# Runs in CI after `npx cap add android`: icons, splash, media scanner plugin, permissions.
from PIL import Image,ImageDraw
import glob,os,re,shutil
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

# ---- startup: no logo on the system splash. Black screen (or your own splash.png), then the animated intro in the app ----
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
if pic and os.path.isdir('www'):shutil.copy('splash.png','www/splash.png')

# ---- media scanner plugin (audio + video from the phone's media library) ----
J='android/app/src/main/java/com/hudsify/app/'
open(J+'MediaLibraryPlugin.java','w').write(r'''package com.hudsify.app;

import android.Manifest;
import android.content.ContentUris;
import android.content.Intent;
import android.database.Cursor;
import android.graphics.Bitmap;
import android.net.Uri;
import android.os.Build;
import android.provider.MediaStore;
import android.provider.Settings;
import android.util.Base64;
import android.util.Size;
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
        @Permission(alias = "storage", strings = { Manifest.permission.READ_EXTERNAL_STORAGE })
    }
)
public class MediaLibraryPlugin extends Plugin {

    private String alias() {
        return Build.VERSION.SDK_INT >= 33 ? "media" : "storage";
    }

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
            : new String[] { MediaStore.Audio.Media._ID, MediaStore.Audio.Media.TITLE, MediaStore.Audio.Media.DURATION, MediaStore.Audio.Media.ARTIST, MediaStore.Audio.Media.ALBUM_ID };
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
}
''')
open(J+'MainActivity.java','w').write('''package com.hudsify.app;

import android.os.Bundle;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(MediaLibraryPlugin.class);
        super.onCreate(savedInstanceState);
    }
}
''')
mf='android/app/src/main/AndroidManifest.xml';x=open(mf).read()
assert '</application>' in x
x=x.replace('</application>','</application>\n    <uses-permission android:name="android.permission.READ_MEDIA_AUDIO" />\n    <uses-permission android:name="android.permission.READ_MEDIA_VIDEO" />\n    <uses-permission android:name="android.permission.READ_EXTERNAL_STORAGE" android:maxSdkVersion="32" />',1)
open(mf,'w').write(x)
print('Hudsify android patch done')
