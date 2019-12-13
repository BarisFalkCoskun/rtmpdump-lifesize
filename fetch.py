import re
import argparse
import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
import subprocess
import json
import platform

# Ignore warning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

DOMAINS = ['vc.agrsci.dk', 'vc.au.dk', '130.226.243.18']
domain_regex = '|'.join(re.escape(domain) for domain in DOMAINS)
prefix_regex = '^https?://(?P<domain>%s)' % domain_regex

def main():
		parser = argparse.ArgumentParser()
		parser.add_argument('-f', '--feed', choices='main presentation composited all'.split())
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
		
		response = s.get('https://%s/videos/video/%s/authorize-playback/' % (domain, id), verify=False)
		o = response.json()
		json_string = json.dumps(o)
		assert o['status'] == 0

		try:
				# Get highest quality available
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

		# Removes any illegal characters
		name = "".join(i for i in o['video_name'] if i not in r'\/:*?"<>|')

		try:
				# iOS video (usually full screen presentation video and tiny lecture video in bottom right corner)
				cmd0 = [
						'youtube-dl', '--no-check-certificate', '-o', '%s (composited) [%s].mp4' % (name, id),
						'https://vc.au.dk/videos/video/' + str(id) + '/authorize-playback-ios/1/'
				]
		except Exception:
				pass

		try:
				# Lecture video
				cmd1 = [
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
				cmd2 = [
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
				cmd3 = [
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
		cmd4 = [
				'ffmpeg', '-nostdin', '-hide_banner', '-nostats', '-i',
				'%s (main) [%s]_1.mp4' % (name, id),
				'-c', 'copy', '-y',
				'%s (main) [%s].mp4' % (name, id)
		]

		cmd5 = [
				'rm', '-f', '%s (main) [%s]_1.mp4' % (name, id)
		]

		cmd6 = [
				'ffmpeg', '-nostdin', '-hide_banner', '-nostats', '-i',
				'%s (presentation) [%s]_1.mp4' % (name, id),
				'-c', 'copy', '-y',
				'%s (presentation) [%s].mp4' % (name, id)
		]

		cmd7 = [
				'rm', '-f', '%s (presentation) [%s]_1.mp4' % (name, id)
		]

		cmd8 = [
				'ffmpeg', '-nostdin', '-hide_banner', '-nostats', '-i',
				'%s (composited) [%s]_1.mp4' % (name, id),
				'-c', 'copy', '-y',
				'%s (composited) [%s].mp4' % (name, id)
		]

		cmd9 = [
				'rm', '-f', '%s (composited) [%s]_1.mp4' % (name, id)
		]

		# macOS
		if (platform.system() == "Darwin"):
				env = dict(DYLD_LIBRARY_PATH='rtmpdump/librtmp')
		else:
				env = dict(LD_LIBRARY_PATH='rtmpdump/librtmp')

		if args.feed == 'all':
				try:
						# iOS
						p0 = subprocess.Popen(cmd0)
						p0.wait()
				except Exception:
						pass

				try:
						# Lecture
						p1 = subprocess.Popen(cmd1, env=env)
				except Exception:
						pass

				# Checks if available (not always available for whatever reason)
				if (o['pres_feed']):
						try:
								p2 = subprocess.Popen(cmd2, env=env)
						except Exception:
								pass

				# if (o['composited_feeds']):
				# 		try:
				# 				p3 = subprocess.Popen(cmd3, env=env)
				# 		except Exception:
				# 				pass

				try:
						p1.wait()
				except Exception:
						pass

				if (o['pres_feed']):
						try:
								p2.wait()
						except Exception:
								pass

				# if (o['composited_feeds']):
				# 		try:
				# 				p3.wait()
				# 		except Exception:
				# 				pass

				try:
						# Creates valid version of lecture video
						p4 = subprocess.Popen(cmd4)
						p4.wait()
				except Exception:
						pass
						
				try:
						# Removes the old version
						p5 = subprocess.Popen(cmd5)
						p5.wait()
				except Exception:
						pass
				
				if (o['pres_feed']):
						try:
								# Creates valid version of presentation video
								p6 = subprocess.Popen(cmd6)
								p6.wait()
								# Deletes old version
								p7 = subprocess.Popen(cmd7)
								p7.wait()
						except Exception:
								pass

				# if (len(o['composited_feeds']) > 0):
				# 		try:
				# 				# Creates valid version of composited video
				# 				p8 = subprocess.Popen(cmd8)
				# 				p8.wait()
				# 				# Deletes old version
				# 				p9 = subprocess.Popen(cmd9)
				# 				p9.wait()
				# 		except Exception:
				# 				pass
		elif args.feed == 'presentation':
				if (o['pres_feed']):
						p2 = subprocess.Popen(cmd2, env=env)
						p2.wait()
						p6 = subprocess.Popen(cmd6)
						p6.wait()
						p7 = subprocess.Popen(cmd7)
						p7.wait()
				else:
						print("Sorry, not available")
		elif args.feed == 'composited':
				p0 = subprocess.Popen(cmd0)
				p0.wait()
		else:
				p1 = subprocess.Popen(cmd1, env=env)
				p1.wait()
				p4 = subprocess.Popen(cmd4)
				p4.wait()
				p5 = subprocess.Popen(cmd5)
				p5.wait()

if __name__ == "__main__":
		main()