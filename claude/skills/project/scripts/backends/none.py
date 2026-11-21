"""No tracker: the notes are the whole record. Sync verbs explain themselves and exit."""
import sys


LINK_KEY = None


class Backend:
    name = "none"
    syncs = False

    def __init__(self, profile):
        self.profile = profile

    def _no(self, *_, **__):
        sys.exit("tracker is 'none' in this machine's profile: the notes are the only record, nothing to sync")

    me = my_name = owned = open_owned = get = my_open = transition_via = transition = comment = _no
    comments_since = create = _no

    def url(self, key):
        return ""

    def init_meta(self, args):
        return []
