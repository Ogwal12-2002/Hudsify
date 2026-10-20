# Hudsify CI patch (runs after `npx cap add android`). It stops the build with a clear message if anything is wrong.
import glob,os,re,shutil,sys
from PIL import Image,ImageDraw
def die(m):
    print('HUDSIFY PATCH FAILED:',m);sys.exit(1)
R='android/app/src/main/res/'
def mk(sz,mode):
    S=1024;im=Image.new('RGBA',(S,S),(0,0,0,0));d=ImageDraw.Draw(im);g=(30,215,96,255)
    if mode=='sq':d.rounded_rectangle([0,0,S,S],radius=int(S*.22),fill=g)
    if mode=='rd':d.ellipse([0,0,S,S],fill=g)
    for a,b,c,e in((.30,.27,.40,.73),(.60,.27,.70,.73),(.40,.45,.60,.55)):d.rectangle([a*S,b*S,c*S,e*S],fill=(0,0,0,255))
    return im.resize((sz,sz),Image.LANCZOS)
for dpi,l,f in(('mdpi',48,108),('hdpi',72,162),('xhdpi',96,216),('xxhdpi',144,324),('xxxhdpi',192,432)):
    mk(l,'sq').save(f'{R}mipmap-{dpi}/ic_launcher.png');mk(l,'rd').save(f'{R}mipmap-{dpi}/ic_launcher_round.png');mk(f,'fg').save(f'{R}mipmap-{dpi}/ic_launcher_foreground.png')
open(R+'values/ic_launcher_background.xml','w').write('<?xml version="1.0" encoding="utf-8"?>\n<resources>\n    <color name="ic_launcher_background">#1ED760</color>\n</resources>\n')

# ---- startup: no logo on the system splash (black, or your own splash.png); the animated intro runs inside the app ----
pic=Image.open('splash.png').convert('RGB') if os.path.exists('splash.png') else None
for p in glob.glob(R+'**/splash.png',recursive=True):
    w,h=Image.open(p).size;im=Image.new('RGB',(w,h),(0,0,0))
    if pic:
        k=min(w*.8/pic.width,h*.8/pic.height);q=pic.resize((int(pic.width*k),int(pic.height*k)),Image.LANCZOS);im.paste(q,((w-q.width)//2,(h-q.height)//2))
    im.save(p)
sx=R+'values/styles.xml';s=open(sx).read()
s=re.sub(r'(<style name="AppTheme\.NoActionBarLaunch"[^>]*>)',r'\1\n        <item name="windowSplashScreenBackground">#000000</item>\n        <item name="windowSplashScreenAnimatedIcon">@drawable/splash_icon</item>',s,count=1)
open(sx,'w').write(s)
open(R+'drawable/splash_icon.xml','w').write('<?xml version="1.0" encoding="utf-8"?>\n<vector xmlns:android="http://schemas.android.com/apk/res/android" android:width="24dp" android:height="24dp" android:viewportWidth="24" android:viewportHeight="24">\n    <path android:fillColor="#00000000" android:pathData="M0,0h1v1h-1z"/>\n</vector>\n')
open(R+'drawable/ic_stat_music.xml','w').write('<?xml version="1.0" encoding="utf-8"?>\n<vector xmlns:android="http://schemas.android.com/apk/res/android" android:width="24dp" android:height="24dp" android:viewportWidth="24" android:viewportHeight="24">\n    <path android:fillColor="#FFFFFFFF" android:pathData="M12,3v10.55c-0.59,-0.34 -1.27,-0.55 -2,-0.55 -2.21,0 -4,1.79 -4,4s1.79,4 4,4 4,-1.79 4,-4V7h4V3h-6z"/>\n</vector>\n')
if os.path.isdir('www'):
    if pic:shutil.copy('splash.png','www/splash.png')
    ip='www/index.html'
    if os.path.exists(ip):
        h=open(ip).read()
        if 'hs-patch' not in h:open(ip,'w').write(h.replace('</head>','<meta name="hs-patch" content="v4"></head>',1))

# ---- native layer: media scanner, notification + lock-screen controls, video-player controls ----
PLUGIN=r'''package __PKG__;

import android.Manifest;
import android.app.Activity;
import android.app.PictureInPictureParams;
import android.content.ContentUris;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ActivityInfo;
import android.database.Cursor;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.media.AudioManager;
import android.media.MediaExtractor;
import android.media.MediaFormat;
import android.net.Uri;
import android.os.Build;
import android.provider.MediaStore;
import android.provider.Settings;
import android.util.Base64;
import android.util.Rational;
import android.util.Size;
import android.view.View;
import android.view.Window;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.view.WindowManager;
import com.getcapacitor.JSArray;
import com.getcapacitor.JSObject;
import com.getcapacitor.PermissionState;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.annotation.Permission;
import com.getcapacitor.annotation.PermissionCallback;
import java.io.ByteArrayOutputStream;

@CapacitorPlugin(
    name = "MediaLibrary",
    permissions = {
        @Permission(alias = "media", strings = { Manifest.permission.READ_MEDIA_AUDIO, Manifest.permission.READ_MEDIA_VIDEO }),
        @Permission(alias = "storage", strings = { Manifest.permission.READ_EXTERNAL_STORAGE }),
        @Permission(alias = "notif", strings = { Manifest.permission.POST_NOTIFICATIONS })
    }
)
public class MediaLibraryPlugin extends Plugin {

    static MediaLibraryPlugin inst;
    static volatile boolean autoPip = false;

    @Override
    public void load() {
        inst = this;
    }

    static void fire(String action, double pos) {
        if (inst == null) return;
        JSObject o = new JSObject();
        o.put("action", action);
        o.put("pos", pos);
        inst.notifyListeners("mediaAction", o);
    }

    static void firePip(boolean on) {
        if (inst == null) return;
        JSObject o = new JSObject();
        o.put("on", on);
        inst.notifyListeners("pipChanged", o);
    }

    private String alias() {
        return Build.VERSION.SDK_INT >= 33 ? "media" : "storage";
    }

    /* ---------- media library ---------- */

    @PluginMethod
    public void status(PluginCall call) {
        JSObject o = new JSObject();
        o.put("granted", getPermissionState(alias()) == PermissionState.GRANTED);
        call.resolve(o);
    }

    @PluginMethod
    public void scan(PluginCall call) {
        if (getPermissionState(alias()) != PermissionState.GRANTED) {
            requestPermissionForAlias(alias(), call, "permCb");
            return;
        }
        doScan(call);
    }

    @PermissionCallback
    private void permCb(PluginCall call) {
        if (getPermissionState(alias()) == PermissionState.GRANTED) doScan(call);
        else call.reject("denied");
    }

    private void collect(JSArray arr, boolean video) {
        Uri base = video ? MediaStore.Video.Media.EXTERNAL_CONTENT_URI : MediaStore.Audio.Media.EXTERNAL_CONTENT_URI;
        String[] proj = video
            ? new String[] { MediaStore.Video.Media._ID, MediaStore.Video.Media.TITLE, MediaStore.Video.Media.DURATION, MediaStore.Video.Media.BUCKET_DISPLAY_NAME }
            : new String[] { MediaStore.Audio.Media._ID, MediaStore.Audio.Media.TITLE, MediaStore.Audio.Media.DURATION, MediaStore.Audio.Media.ARTIST, MediaStore.Audio.Media.ALBUM_ID, MediaStore.Audio.Media.ALBUM };
        String sel = video ? null : MediaStore.Audio.Media.IS_MUSIC + " != 0";
        try (Cursor c = getContext().getContentResolver().query(base, proj, sel, null, "date_added DESC")) {
            while (c != null && c.moveToNext()) {
                long id = c.getLong(0);
                JSObject o = new JSObject();
                o.put("id", id);
                o.put("kind", video ? "v" : "a");
                o.put("title", c.getString(1));
                o.put("dur", c.getLong(2) / 1000.0);
                if (video) {
                    o.put("folder", c.getString(3));
                } else {
                    o.put("artist", c.getString(3));
                    o.put("aid", c.getLong(4));
                    o.put("album", c.getString(5));
                }
                o.put("uri", ContentUris.withAppendedId(base, id).toString());
                arr.put(o);
            }
        } catch (Exception e) {
            // this collection is not readable (permission not granted): skip it
        }
    }

    private void doScan(PluginCall call) {
        JSArray arr = new JSArray();
        collect(arr, false);
        collect(arr, true);
        JSObject r = new JSObject();
        r.put("tracks", arr);
        call.resolve(r);
    }

    @PluginMethod
    public void art(PluginCall call) {
        String uri = call.getString("uri");
        Integer sz = call.getInt("size", 300);
        JSObject r = new JSObject();
        if (uri == null || Build.VERSION.SDK_INT < 29) {
            call.resolve(r);
            return;
        }
        try {
            Bitmap b = getContext().getContentResolver().loadThumbnail(Uri.parse(uri), new Size(sz, sz), null);
            ByteArrayOutputStream bo = new ByteArrayOutputStream();
            b.compress(Bitmap.CompressFormat.JPEG, 82, bo);
            r.put("data", "data:image/jpeg;base64," + Base64.encodeToString(bo.toByteArray(), Base64.NO_WRAP));
        } catch (Exception e) {
            // no artwork for this file
        }
        call.resolve(r);
    }

    @PluginMethod
    public void openSettings(PluginCall call) {
        Intent i = new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:" + getContext().getPackageName()));
        i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        getContext().startActivity(i);
        call.resolve();
    }

    @PluginMethod
    public void info(PluginCall call) {
        String us = call.getString("uri");
        JSObject r = new JSObject();
        if (us == null) {
            call.resolve(r);
            return;
        }
        Uri u = Uri.parse(us);
        MediaExtractor ex = new MediaExtractor();
        try {
            ex.setDataSource(getContext(), u, null);
            JSArray au = new JSArray();
            JSArray su = new JSArray();
            for (int i = 0; i < ex.getTrackCount(); i++) {
                MediaFormat f = ex.getTrackFormat(i);
                String m = f.getString(MediaFormat.KEY_MIME);
                if (m == null) continue;
                String lang = f.containsKey(MediaFormat.KEY_LANGUAGE) ? f.getString(MediaFormat.KEY_LANGUAGE) : "";
                if (m.startsWith("video/")) {
                    r.put("vcodec", m);
                    try {
                        if (f.containsKey(MediaFormat.KEY_FRAME_RATE)) r.put("fps", f.getInteger(MediaFormat.KEY_FRAME_RATE));
                    } catch (Exception e1) {
                        try {
                            r.put("fps", (double) f.getFloat(MediaFormat.KEY_FRAME_RATE));
                        } catch (Exception e2) {
                            // unknown frame rate
                        }
                    }
                    if (f.containsKey(MediaFormat.KEY_WIDTH)) r.put("w", f.getInteger(MediaFormat.KEY_WIDTH));
                    if (f.containsKey(MediaFormat.KEY_HEIGHT)) r.put("h", f.getInteger(MediaFormat.KEY_HEIGHT));
                } else if (m.startsWith("audio/")) {
                    JSObject o = new JSObject();
                    o.put("codec", m);
                    o.put("lang", lang);
                    au.put(o);
                } else {
                    JSObject o = new JSObject();
                    o.put("codec", m);
                    o.put("lang", lang);
                    su.put(o);
                }
            }
            r.put("audio", au);
            r.put("subs", su);
        } catch (Exception e) {
            // not readable as a media container
        } finally {
            try {
                ex.release();
            } catch (Exception e3) {
                // ignore
            }
        }
        try (Cursor c = getContext().getContentResolver().query(u, new String[] { MediaStore.MediaColumns.DISPLAY_NAME, MediaStore.MediaColumns.SIZE, MediaStore.MediaColumns.MIME_TYPE }, null, null, null)) {
            if (c != null && c.moveToFirst()) {
                r.put("name", c.getString(0));
                r.put("size", c.getLong(1));
                r.put("mime", c.getString(2));
            }
        } catch (Exception e4) {
            // ignore
        }
        try (Cursor c = getContext().getContentResolver().query(u, new String[] { "relative_path" }, null, null, null)) {
            if (c != null && c.moveToFirst()) r.put("path", c.getString(0));
        } catch (Exception e5) {
            // ignore
        }
        call.resolve(r);
    }

    /* ---------- video player: screen, brightness, volume, orientation, picture-in-picture ---------- */

    @PluginMethod
    public void setImmersive(final PluginCall call) {
        final boolean on = Boolean.TRUE.equals(call.getBoolean("on", false));
        final Activity a = getActivity();
        a.runOnUiThread(new Runnable() {
            @Override
            public void run() {
                try {
                    Window w = a.getWindow();
                    if (Build.VERSION.SDK_INT >= 30) {
                        WindowInsetsController c = w.getInsetsController();
                        if (c != null) {
                            if (on) {
                                c.hide(WindowInsets.Type.systemBars());
                                c.setSystemBarsBehavior(WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE);
                            } else {
                                c.show(WindowInsets.Type.systemBars());
                            }
                        }
                    } else {
                        int flags = View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION | View.SYSTEM_UI_FLAG_FULLSCREEN
                            | View.SYSTEM_UI_FLAG_LAYOUT_STABLE | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN;
                        w.getDecorView().setSystemUiVisibility(on ? flags : View.SYSTEM_UI_FLAG_VISIBLE);
                    }
                } catch (Exception e) {
                    // keep going
                }
                call.resolve();
            }
        });
    }

    @PluginMethod
    public void setOrientation(final PluginCall call) {
        String m = call.getString("mode", "auto");
        final int o = "landscape".equals(m) ? ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE
            : "portrait".equals(m) ? ActivityInfo.SCREEN_ORIENTATION_PORTRAIT
            : ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED;
        final Activity a = getActivity();
        a.runOnUiThread(new Runnable() {
            @Override
            public void run() {
                try {
                    a.setRequestedOrientation(o);
                } catch (Exception e) {
                    // ignore
                }
                call.resolve();
            }
        });
    }

    @PluginMethod
    public void getBrightness(PluginCall call) {
        Activity a = getActivity();
        float b = a.getWindow().getAttributes().screenBrightness;
        if (b < 0) {
            try {
                b = Settings.System.getInt(a.getContentResolver(), Settings.System.SCREEN_BRIGHTNESS) / 255f;
            } catch (Exception e) {
                b = 0.5f;
            }
        }
        JSObject r = new JSObject();
        r.put("v", b);
        call.resolve(r);
    }

    @PluginMethod
    public void setBrightness(final PluginCall call) {
        final double v = call.getDouble("v", 0.5);
        final Activity a = getActivity();
        a.runOnUiThread(new Runnable() {
            @Override
            public void run() {
                try {
                    Window w = a.getWindow();
                    WindowManager.LayoutParams lp = w.getAttributes();
                    lp.screenBrightness = (float) Math.max(0.01, Math.min(1.0, v));
                    w.setAttributes(lp);
                } catch (Exception e) {
                    // ignore
                }
                call.resolve();
            }
        });
    }

    @PluginMethod
    public void getVolume(PluginCall call) {
        AudioManager am = (AudioManager) getContext().getSystemService(Context.AUDIO_SERVICE);
        int max = Math.max(1, am.getStreamMaxVolume(AudioManager.STREAM_MUSIC));
        JSObject r = new JSObject();
        r.put("v", am.getStreamVolume(AudioManager.STREAM_MUSIC) / (double) max);
        call.resolve(r);
    }

    @PluginMethod
    public void setVolume(PluginCall call) {
        double v = call.getDouble("v", 0.5);
        AudioManager am = (AudioManager) getContext().getSystemService(Context.AUDIO_SERVICE);
        int max = Math.max(1, am.getStreamMaxVolume(AudioManager.STREAM_MUSIC));
        am.setStreamVolume(AudioManager.STREAM_MUSIC, (int) Math.round(Math.max(0.0, Math.min(1.0, v)) * max), 0);
        call.resolve();
    }

    @PluginMethod
    public void pip(final PluginCall call) {
        if (Build.VERSION.SDK_INT < 26) {
            call.reject("unsupported");
            return;
        }
        final Activity a = getActivity();
        a.runOnUiThread(new Runnable() {
            @Override
            public void run() {
                try {
                    a.enterPictureInPictureMode(new PictureInPictureParams.Builder().setAspectRatio(new Rational(16, 9)).build());
                    call.resolve();
                } catch (Exception e) {
                    call.reject(String.valueOf(e.getMessage()));
                }
            }
        });
    }

    @PluginMethod
    public void setAutoPip(PluginCall call) {
        autoPip = Boolean.TRUE.equals(call.getBoolean("on", false));
        call.resolve();
    }

    /* ---------- notification banner + lock-screen controls ---------- */

    @PluginMethod
    public void requestNotif(PluginCall call) {
        if (Build.VERSION.SDK_INT >= 33 && getPermissionState("notif") != PermissionState.GRANTED) {
            requestPermissionForAlias("notif", call, "notifCb");
            return;
        }
        call.resolve();
    }

    @PermissionCallback
    private void notifCb(PluginCall call) {
        call.resolve();
    }

    @PluginMethod
    public void mediaUpdate(PluginCall call) {
        String title = call.getString("title", "");
        String artist = call.getString("artist", "");
        String album = call.getString("album", "");
        String art = call.getString("art", "");
        boolean playing = Boolean.TRUE.equals(call.getBoolean("playing", false));
        long pos = call.getDouble("pos", 0.0).longValue();
        long dur = call.getDouble("dur", 0.0).longValue();
        Bitmap bmp = null;
        if (art != null && art.length() > 10) {
            try {
                byte[] b = Base64.decode(art, Base64.DEFAULT);
                bmp = BitmapFactory.decodeByteArray(b, 0, b.length);
            } catch (Exception e) {
                bmp = null;
            }
        }
        MediaService.update(getContext(), title, artist, album, bmp, playing, pos, dur);
        call.resolve();
    }

    @PluginMethod
    public void mediaStop(PluginCall call) {
        MediaService.stop();
        call.resolve();
    }
}
'''
SERVICE=r'''package __PKG__;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.graphics.Bitmap;
import android.graphics.drawable.Icon;
import android.media.MediaMetadata;
import android.media.session.MediaSession;
import android.media.session.PlaybackState;
import android.os.Build;
import android.os.IBinder;

public class MediaService extends Service {
    static final String CH = "hudsify_playback";
    static final int ID = 7711;
    static MediaService inst;
    static String sTitle = "";
    static String sArtist = "";
    static String sAlbum = "";
    static Bitmap sArt;
    static boolean sPlaying;
    static long sPos;
    static long sDur;
    private MediaSession session;

    static void update(Context c, String title, String artist, String album, Bitmap art, boolean playing, long pos, long dur) {
        sTitle = title == null ? "" : title;
        sArtist = artist == null ? "" : artist;
        sAlbum = album == null ? "" : album;
        sArt = art;
        sPlaying = playing;
        sPos = pos;
        sDur = dur;
        if (inst != null) {
            inst.refresh();
            return;
        }
        try {
            Intent i = new Intent(c, MediaService.class);
            if (Build.VERSION.SDK_INT >= 26) c.startForegroundService(i);
            else c.startService(i);
        } catch (Exception e) {
            // the system does not allow starting it right now
        }
    }

    static void stop() {
        if (inst != null) inst.shutdown();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    @Override
    public void onCreate() {
        super.onCreate();
        inst = this;
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationChannel ch = new NotificationChannel(CH, "Playback", NotificationManager.IMPORTANCE_LOW);
            ch.setShowBadge(false);
            ch.setLockscreenVisibility(Notification.VISIBILITY_PUBLIC);
            getSystemService(NotificationManager.class).createNotificationChannel(ch);
        }
        session = new MediaSession(this, "Hudsify");
        session.setCallback(new MediaSession.Callback() {
            @Override
            public void onPlay() {
                MediaLibraryPlugin.fire("play", 0);
            }

            @Override
            public void onPause() {
                MediaLibraryPlugin.fire("pause", 0);
            }

            @Override
            public void onSkipToNext() {
                MediaLibraryPlugin.fire("next", 0);
            }

            @Override
            public void onSkipToPrevious() {
                MediaLibraryPlugin.fire("prev", 0);
            }

            @Override
            public void onSeekTo(long pos) {
                MediaLibraryPlugin.fire("seek", pos / 1000.0);
            }
        });
        session.setActive(true);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        String a = intent == null ? null : intent.getAction();
        if (a == null) {
            try {
                Notification n = build();
                if (Build.VERSION.SDK_INT >= 29) startForeground(ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK);
                else startForeground(ID, n);
            } catch (Exception e) {
                // foreground start refused
            }
            refresh();
        } else if (a.equals("hs.play")) {
            MediaLibraryPlugin.fire("play", 0);
        } else if (a.equals("hs.pause")) {
            MediaLibraryPlugin.fire("pause", 0);
        } else if (a.equals("hs.next")) {
            MediaLibraryPlugin.fire("next", 0);
        } else if (a.equals("hs.prev")) {
            MediaLibraryPlugin.fire("prev", 0);
        }
        return START_NOT_STICKY;
    }

    void refresh() {
        if (session == null) return;
        MediaMetadata.Builder mb = new MediaMetadata.Builder()
            .putString(MediaMetadata.METADATA_KEY_TITLE, sTitle)
            .putString(MediaMetadata.METADATA_KEY_ARTIST, sArtist)
            .putString(MediaMetadata.METADATA_KEY_ALBUM, sAlbum)
            .putLong(MediaMetadata.METADATA_KEY_DURATION, sDur);
        if (sArt != null) {
            mb.putBitmap(MediaMetadata.METADATA_KEY_ALBUM_ART, sArt);
            mb.putBitmap(MediaMetadata.METADATA_KEY_ART, sArt);
        }
        session.setMetadata(mb.build());
        long actions = PlaybackState.ACTION_PLAY | PlaybackState.ACTION_PAUSE | PlaybackState.ACTION_PLAY_PAUSE
            | PlaybackState.ACTION_SKIP_TO_NEXT | PlaybackState.ACTION_SKIP_TO_PREVIOUS | PlaybackState.ACTION_SEEK_TO;
        session.setPlaybackState(new PlaybackState.Builder().setActions(actions)
            .setState(sPlaying ? PlaybackState.STATE_PLAYING : PlaybackState.STATE_PAUSED, sPos, sPlaying ? 1f : 0f).build());
        Notification n = build();
        try {
            if (sPlaying) {
                if (Build.VERSION.SDK_INT >= 29) startForeground(ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK);
                else startForeground(ID, n);
            } else {
                stopForeground(false);
                getSystemService(NotificationManager.class).notify(ID, n);
            }
        } catch (Exception e) {
            // ignore
        }
    }

    private Notification build() {
        Notification.Builder b = Build.VERSION.SDK_INT >= 26 ? new Notification.Builder(this, CH) : new Notification.Builder(this);
        int small = getResources().getIdentifier("ic_stat_music", "drawable", getPackageName());
        if (small == 0) small = android.R.drawable.ic_media_play;
        Intent open = getPackageManager().getLaunchIntentForPackage(getPackageName());
        b.setSmallIcon(small)
            .setContentTitle(sTitle)
            .setContentText(sArtist)
            .setVisibility(Notification.VISIBILITY_PUBLIC)
            .setOnlyAlertOnce(true)
            .setOngoing(sPlaying)
            .setShowWhen(false)
            .setCategory(Notification.CATEGORY_TRANSPORT);
        if (sAlbum != null && sAlbum.length() > 0) b.setSubText(sAlbum);
        if (open != null) b.setContentIntent(PendingIntent.getActivity(this, 0, open, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT));
        if (sArt != null) b.setLargeIcon(sArt);
        b.addAction(act(android.R.drawable.ic_media_previous, "Previous", "hs.prev", 1));
        if (sPlaying) b.addAction(act(android.R.drawable.ic_media_pause, "Pause", "hs.pause", 2));
        else b.addAction(act(android.R.drawable.ic_media_play, "Play", "hs.play", 2));
        b.addAction(act(android.R.drawable.ic_media_next, "Next", "hs.next", 3));
        b.setStyle(new Notification.MediaStyle().setMediaSession(session.getSessionToken()).setShowActionsInCompactView(0, 1, 2));
        return b.build();
    }

    private Notification.Action act(int icon, String label, String action, int req) {
        Intent i = new Intent(this, MediaService.class).setAction(action);
        PendingIntent pi = PendingIntent.getService(this, req, i, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        return new Notification.Action.Builder(Icon.createWithResource(this, icon), label, pi).build();
    }

    void shutdown() {
        try {
            stopForeground(true);
            getSystemService(NotificationManager.class).cancel(ID);
        } catch (Exception e) {
            // ignore
        }
        stopSelf();
    }

    @Override
    public void onTaskRemoved(Intent rootIntent) {
        shutdown();
        super.onTaskRemoved(rootIntent);
    }

    @Override
    public void onDestroy() {
        if (session != null) {
            session.release();
            session = null;
        }
        inst = null;
        super.onDestroy();
    }
}
'''
MAIN=r'''package __PKG__;

import android.app.PictureInPictureParams;
import android.content.res.Configuration;
import android.os.Build;
import android.os.Bundle;
import android.util.Rational;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(MediaLibraryPlugin.class);
        super.onCreate(savedInstanceState);
    }

    @Override
    public void onUserLeaveHint() {
        super.onUserLeaveHint();
        if (MediaLibraryPlugin.autoPip && Build.VERSION.SDK_INT >= 26) {
            try {
                enterPictureInPictureMode(new PictureInPictureParams.Builder().setAspectRatio(new Rational(16, 9)).build());
            } catch (Exception e) {
                // not available right now
            }
        }
    }

    @Override
    public void onPictureInPictureModeChanged(boolean isInPictureInPictureMode, Configuration newConfig) {
        super.onPictureInPictureModeChanged(isInPictureInPictureMode, newConfig);
        MediaLibraryPlugin.firePip(isInPictureInPictureMode);
    }
}
'''
mains=glob.glob('android/app/src/main/java/**/MainActivity.java',recursive=True)
if not mains:die('MainActivity.java not found (did "npx cap add android" run?)')
PKG=re.search(r'package\s+([\w.]+);',open(mains[0]).read()).group(1)
J=os.path.dirname(mains[0])+'/'
for name,src in (('MediaLibraryPlugin.java',PLUGIN),('MediaService.java',SERVICE),('MainActivity.java',MAIN)):
    open(J+name,'w').write(src.replace('__PKG__',PKG))
mf='android/app/src/main/AndroidManifest.xml';x=open(mf).read()
if '</application>' not in x:die('AndroidManifest.xml has no </application>')
x=re.sub(r'<activity\b(?![^>]*supportsPictureInPicture)','<activity android:supportsPictureInPicture="true"',x,count=1)
x=x.replace('</application>','    <service android:name="'+PKG+'.MediaService" android:exported="false" android:foregroundServiceType="mediaPlayback" />\n    </application>',1)
perms=['READ_MEDIA_AUDIO','READ_MEDIA_VIDEO','POST_NOTIFICATIONS','FOREGROUND_SERVICE','FOREGROUND_SERVICE_MEDIA_PLAYBACK','WAKE_LOCK']
add=''.join('    <uses-permission android:name="android.permission.%s" />\n'%p for p in perms)+'    <uses-permission android:name="android.permission.READ_EXTERNAL_STORAGE" android:maxSdkVersion="32" />\n'
x=x.replace('</application>','</application>\n'+add,1)
open(mf,'w').write(x)
# self-check: stop the build now (instead of shipping a broken app) if anything is missing
chk=open(J+'MainActivity.java').read()
assert 'registerPlugin(MediaLibraryPlugin.class)' in chk,'MainActivity not patched'
for f in ('MediaLibraryPlugin.java','MediaService.java'):
    if not os.path.exists(J+f):die(f+' missing')
mx=open(mf).read()
for need in ('MediaService','READ_MEDIA_AUDIO','POST_NOTIFICATIONS','supportsPictureInPicture'):
    if need not in mx:die('manifest is missing '+need)
print('Hudsify android patch v4 OK  (package %s)'%PKG)
