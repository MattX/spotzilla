import youtube_dl
import pylast
from difflib import SequenceMatcher
import eyed3
import configparser
import sys

CONFIDENCE_THRESHOLD = 0.8


class BColors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def bold(s):
    return BColors.BOLD + s + BColors.ENDC


def similar(a, b):
    return SequenceMatcher(None, a, b).ratio()


class VariableHook:
    def __init__(self):
        self.hook = self.hookwarning

    def hookwarning(self, d):
        print("Warning: called unregistered hook!")

    def set_hook(self, h):
        self.hook = h

    def forward_hook(self, d):
        self.hook(d)


class SilentLogger(object):
    def debug(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        print(msg)


class Track:
    def __init__(self, fname, vid_title, title, artist, search_results, need_help):
        self.fname = fname
        self.vid_title = vid_title
        self.title = title
        self.artist = artist
        self.search_results = search_results
        self.need_help = need_help

    def write(self):
        l = eyed3.load(self.fname)
        if self.artist:
            l.tag.artist = self.artist
        if self.title:
            l.tag.title = self.title
        l.tag.save()


def get_lastfm_network():
    c = configparser.ConfigParser()
    with open('settings') as cf:
        c.read_file(cf)
    c = c['auth']
    return pylast.LastFMNetwork(api_key=c['api_key'], api_secret=c['secret'], username=c['username'], password_hash=c['password_hash'])


def download(url, ytdl, vh, tracks, network):
    """
    Do the heavy lifting
    """
    filename = None
    def hook(d):
        nonlocal filename
        if filename is None and d['status'] in ["downloading", "finished"]:
            filename = d['filename']
        if d['status'] == "downloading":
            print("\r   Downloading...          ", end="")
        elif d['status'] == "finished":
            print("\r   Converting...          ", end="")
        sys.stdout.flush()
    vh.set_hook(hook)

    print("{}=> Downloading {}.{}".format(BColors.HEADER, url, BColors.ENDC))
    print("   Starting", end="")
    info = ytdl.extract_info(url, download=True)
    print("\r   Done.           ")
    
    vid_title = info["title"]
    print("   Video title is {}. Querying on last.fm... ".format(vid_title), end="")
    r = network.search_for_track("", vid_title)
    count = r.get_total_result_count()
    r = r.get_next_page()

    track = Track(None, vid_title, None, None, r, True)
    presumed_title = None
    presumed_artist = None

    if count == 0:
        print("No results found.")
        score = 0
    else:
        best_title = r[0].title
        best_artist = r[0].artist.name
        print("\n   Best found: {} - {}. ".format(bold(best_artist), bold(best_title)), end="")
        parts = [p.strip() for p in vid_title.split("-")]
        if len(parts) == 1:
            presumed_title = parts[0]
            score = similar(presumed_title, best_title)
        elif len(parts) == 2:
            presumed_artist = parts[0]
            presumed_title = parts[1]
            score = max(similar(parts[0], best_title) + similar(parts[1], best_artist),
                        similar(parts[1], best_title) + similar(parts[0], best_artist)) / 2
        else:
            score = 0

        print("Confidence: {:.0f}%. ".format(score*100), end="")

    # Spin just in case the hook hasn't been called
    while filename is None:
        pass

    track.fname = ".".join(filename.split(".")[:-2] + ["mp3"])

    if score > CONFIDENCE_THRESHOLD:
        print("{}Saving information.{}".format(BColors.OKGREEN, BColors.ENDC))
        track.artist = best_artist
        track.title = best_title
        track.need_help = False
        track.write()
    else:
        print("{}I'll need some help.{}".format(BColors.WARNING, BColors.ENDC))
        track.artist = presumed_artist
        track.title = presumed_title

    tracks.append(track)


vh = VariableHook()
ydl_opts = {
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            }],
        'progress_hooks': [vh.forward_hook],
        'outtmpl': "%(title)s.%(id)s.%(ext)s",
        'logger': SilentLogger()
        }

tracks = []

network = get_lastfm_network()

with youtube_dl.YoutubeDL(ydl_opts) as ytdl:
    for track in sys.argv[1:]:
        download(track, ytdl, vh, tracks, network)
        print()

print("=> Downloading done.")

for track in tracks:
    if track.need_help:
        continue
    
    print("   Track {}: written as {} - {}.".format(bold(track.vid_title), bold(track.artist), bold(track.title)))


for track in tracks:
    if not track.need_help:
        continue

    print("   Track {}:".format(bold(track.vid_title)))
    in_artist = input("     Artist [{}]? ".format(track.artist)).strip()
    if in_artist:
        track.artist = in_artist

    in_title = input("     Title [{}]? ".format(track.title)).strip()
    if in_title:
        track.title = in_title

    track.write()

print("=> All set.")

