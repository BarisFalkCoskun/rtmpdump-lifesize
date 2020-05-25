#!/usr/local/bin/python3

import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
import subprocess
import platform
import argparse
import json
import re

DOMAINS = ['vc.agrsci.dk', 'vc.au.dk', '130.226.243.18']
domain_regex = '|'.join(re.escape(domain) for domain in DOMAINS)
prefix_regex = '^https?://(?P<domain>%s)' % domain_regex

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

# python3 fetch.py -f all http://vc.au.dk/videos/video/1234/

def valid_filename(i):
    if (i.isalnum() or i == ' ' or i in r'-_.,' or i.isdigit()):
        return True

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-f', '--feed',
                        choices='main presentation all composited'.split())
    parser.add_argument('-u', '--username')
    parser.add_argument('-p', '--password')
    parser.add_argument('url')
    args = parser.parse_args()

    mo = re.match(prefix_regex + r'/videos/video/(?P<id>\d+)/$', args.url)
    if mo is None:
        parser.error("Invalid URL")
    id = int(mo.group('id'))
    domain = mo.group('domain')

    s = requests.Session()
    # Force HTTPS
    response = s.get('https://%s/videos/video/%s/' % (domain, id), verify=False)
    if response.history:
        # We were redirected, so a login is probably needed
        token_pattern = (r"<input type='hidden' name='csrfmiddlewaretoken' " +
                         r"value='([^']+)' />")
        mo = re.search(token_pattern, response.text)
        assert mo is not None
        if not args.username or not args.password:
            parser.error("Login required")
        referer = response.url
        response = s.post(
            response.url,
            data=dict(username=args.username, password=args.password,
                        csrfmiddlewaretoken=mo.group(1)),
            headers=dict(referer=referer))
        assert response.status_code == 200, response.status_code
    response = s.get(
        'https://%s/videos/video/%s/authorize-playback/' % (domain, id), verify=False)
    o = response.json()
    json_string = json.dumps(o)
    assert o['status'] == 0

    print(id)

    try:
        path1 = o['main_feeds'][len(o['main_feeds']) - 1]
        path1 = path1[len(path1) - 1]
    except Exception:
        pass

    path2 = o['pres_feed']

    try:
        path3 = o['composited_feeds'][len(o['composited_feeds']) - 1]
        path3 = path3[len(path3) - 1]
    except Exception:
        pass

    streamer = o['streamer']
    mo = re.match(r'([^/]+)/(.*)', streamer)
    hostname = mo.group(1)
    streamer_path = mo.group(2)
    token = o['playback_token']
    print("Playback token is %s" % token)

    name = o['video_name']
    name = name.replace("&", "and")
    name = "".join(i for i in name if valid_filename(i))

    try:
        dlIOSCmd = [
            'youtube-dl', '--no-check-certificate', '-o', '%s (composited) [%s].mp4' % (name, id),
            'https://vc.au.dk/videos/video/' + str(id) + '/authorize-playback-ios/1/'
        ]
    except Exception:
        pass

    try:
        # Lecture video
        dlMainCmd = [
            'rtmpdump/rtmpdump','-v', '-r',
            'rtmp://%s:1935' % hostname + '/' + streamer_path + '/' + path1,
            '-a', streamer_path,
            '-t', 'rtmp://%s:1935' % hostname + '/' + streamer_path,
            '-f', 'LNX 11,2,202,569',
            # Note O:2 means "ECMA Array" and requires a patched rtmpdump
            '-C', 'O:2', '-C', 'NN:0:%s' % token, '-C', 'NB:1:0',
            '-y', path1,
            '-o', '%s (main) [%s]_1.mp4' % (name, id),
        ]
    except Exception:
        pass

    try:
        # Presentation video
        dlPresCmd = [
            'rtmpdump/rtmpdump', '-v', '-r',
            'rtmp://%s:1935' % hostname + '/' + streamer_path + '/' + path2,
            '-a', streamer_path,
            '-t', 'rtmp://%s:1935' % hostname + '/' + streamer_path,
            '-f', 'LNX 11,2,202,569',
            '-C', 'O:2', '-C', 'NN:0:%s' % token, '-C', 'NB:1:0',
            '-y', path2,
            '-o', '%s (presentation) [%s]_1.mp4' % (name, id),
        ]
    except Exception:
        pass

    try:
        # Composited video
        dlCompositedCmd = [
            'rtmpdump/rtmpdump', '-v', '-r',
            'rtmp://%s:1935' % hostname + '/' + streamer_path + '/' + path3,
            '-a', streamer_path,
            '-t', 'rtmp://%s:1935' % hostname + '/' + streamer_path,
            '-f', 'LNX 11,2,202,569',
            '-C', 'O:2', '-C', 'NN:0:%s' % token, '-C', 'NB:1:0',
            '-y', path3,
            '-o', '%s (composited) [%s]_1.mp4' % (name, id),
        ]
    except Exception:
        pass

    # Creates a valid version of video, otherwise it won't be playable in many video players
    validMainCmd = [
        'ffmpeg', '-nostdin', '-hide_banner', '-nostats', '-i',
        '%s (main) [%s]_1.mp4' % (name, id),
        '-c', 'copy', '-y',
        '%s (main) [%s].mp4' % (name, id)
    ]

    extractMainAudioCmd = [
        'ffmpeg', '-nostdin', '-hide_banner', '-nostats', '-i',
        '%s (main) [%s].mp4' % (name, id),
        '-vn', '-acodec', 'copy', 'main-%s.aac' % (id)
    ]

    deleteMainCmd = [
        'rm', '-f', '%s (main) [%s]_1.mp4' % (name, id)
    ]

    importMainAudioCmd = [
        'ffmpeg', '-nostdin', '-hide_banner', '-nostats', '-i',
        '%s (presentation) [%s]_1.mp4' % (name, id),
        '-i', 'main-%s.aac' % (id), '-c', 'copy', '-y',
        '%s (presentation) [%s].mp4' % (name, id)
    ]

    deleteMainAudioCmd = [
        'rm', '-f', 'main-%s.aac' % (id)
    ]

    validPresCmd = [
        'ffmpeg', '-nostdin', '-hide_banner', '-nostats', '-i',
        '%s (presentation) [%s]_1.mp4' % (name, id),
        '-c', 'copy', '-y',
        '%s (presentation) [%s].mp4' % (name, id)
    ]

    deletePresCmd = [
        'rm', '-f', '%s (presentation) [%s]_1.mp4' % (name, id)
    ]

    validCompositedCmd = [
        'ffmpeg', '-nostdin', '-hide_banner', '-nostats', '-i',
        '%s (composited) [%s]_1.mp4' % (name, id),
        '-c', 'copy', '-y',
        '%s (composited) [%s].mp4' % (name, id)
    ]

    deleteCompositedCmd = [
        'rm', '-f', '%s (composited) [%s]_1.mp4' % (name, id)
    ]

    # macOS
    if (platform.system() == "Darwin"):
            env = dict(DYLD_LIBRARY_PATH='rtmpdump/librtmp')
    else:
            env = dict(LD_LIBRARY_PATH='rtmpdump/librtmp')

    if args.feed == 'all':
        if (o['is_live']):
            while (o['is_live']):
                # Sleep an hour and check if lecture is done
                time.sleep(3600)
                response = s.get('https://%s/videos/video/%s/authorize-playback/' % (domain, id), verify=False)
                o = response.json()
                assert o['status'] == 0

        try:
            dlIOS = subprocess.Popen(dlIOSCmd)
            dlIOS.wait()

            if (dlIOS.returncode != 0 and o['composited_feeds']):
                dlComposited = subprocess.Popen(dlCompositedCmd, env=env)
        except Exception:
            pass

        try:
            dlMain = subprocess.Popen(dlMainCmd, env=env)
        except Exception:
            pass

        if (o['pres_feed']):
            try:
                dlPres = subprocess.Popen(dlPresCmd, env=env)
            except Exception:
                pass

        try:
            dlMain.wait()
        except Exception:
            pass

        if (o['pres_feed']):
            try:
                dlPres.wait()
            except Exception:
                pass

        try:
            validMain = subprocess.Popen(validMainCmd)
            validMain.wait()
        except Exception:
            pass
        
        try:
            deleteMain = subprocess.Popen(deleteMainCmd)
            deleteMain.wait()
        except Exception:
            pass
        
        if (o['pres_feed']):
            try:
                extractMainAudio = subprocess.Popen(extractMainAudioCmd)
                extractMainAudio.wait()
            except Exception:
                pass
            
            try:
                importMainAudio = subprocess.Popen(importMainAudioCmd)
                importMainAudio.wait()
            except Exception:
                pass

            try:
                deleteMainAudio = subprocess.Popen(deleteMainAudioCmd)
                deleteMainAudio.wait()
            except Exception:
                pass

            try:
                deletePres = subprocess.Popen(deletePresCmd)
                deletePres.wait()
            except Exception:
                pass

        if (dlIOS.returncode != 0 and len(o['composited_feeds']) > 0):
            try:
                dlComposited.wait()

                # Creates valid version of composited video
                validComposited = subprocess.Popen(validCompositedCmd)
                validComposited.wait()

                # Deletes old version
                deleteComposited = subprocess.Popen(deleteCompositedCmd)
                deleteComposited.wait()
            except Exception:
                pass
    elif args.feed == 'presentation':
        dlPres = subprocess.Popen(dlPresCmd, env=env)
        dlPres.wait()

        validPres = subprocess.Popen(validPresCmd)
        validPres.wait()

        deletePres = subprocess.Popen(deletePresCmd)
        deletePres.wait()
    elif args.feed == 'composited':
        dlIOS = subprocess.Popen(dlIOSCmd)
        dlIOS.wait()

        if (dlIOS.returncode != 0 and o['composited_feeds']):
            dlComposited = subprocess.Popen(dlCompositedCmd, env=env)
            dlComposited.wait()

            # Creates valid version of composited video
            validComposited = subprocess.Popen(validCompositedCmd)
            validComposited.wait()

            # Deletes old version
            deleteComposited = subprocess.Popen(deleteCompositedCmd)
            deleteComposited.wait()
    else:
        dlMain = subprocess.Popen(dlMainCmd, env=env)
        dlMain.wait()

        validMain = subprocess.Popen(validMainCmd)
        validMain.wait()

        deleteMain = subprocess.Popen(deleteMainCmd)
        deleteMain.wait()

if __name__ == "__main__":
    main()