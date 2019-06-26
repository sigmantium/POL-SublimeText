import sublime, sublime_plugin
import string
import re
import time
from os.path import basename


MAX_VIEWS = 20
MAX_WORDS_PER_VIEW = 100
MAX_FIX_TIME_SECS_PER_VIEW = 0.01

settings = sublime.load_settings('Autocomplete.sublime-settings')

class PleasurazyAPICompletionsPackage():
  def init(self):
    self.api = {}
    self.settings = sublime.load_settings('Autocomplete.sublime-settings')
    self.API_Setup = self.settings.get('completion_active_list')

    # Caching completions
    if self.API_Setup:
      for API_Keyword in self.API_Setup:
        self.api[API_Keyword] = sublime.load_settings('sbc-api-' + API_Keyword + '.sublime-settings')

    # Caching extended completions(deprecated)
    if self.settings.get('completion_active_extend_list'):
      for API_Keyword in self.settings.get('completion_active_extend_list'):
        self.api[API_Keyword] = sublime.load_settings('sbc-api-' + API_Keyword + '.sublime-settings')



# In Sublime Text 3 things are loaded async, using plugin_loaded() callback before try accessing.
pleasurazy = PleasurazyAPICompletionsPackage()

if int(sublime.version()) < 3000:
  pleasurazy.init()
else:
  def plugin_loaded():
    global pleasurazy
    pleasurazy.init()



class PleasurazyAPICompletionsPackageEventListener(sublime_plugin.EventListener):
  global pleasurazy

  def on_query_completions(self, view, prefix, locations):
    self.completions = []
    words = []
    other_views = [
        v
        for v in sublime.active_window().views()
        if v.id != view.id
    ]
    views = [view] + other_views
    views = views[0:MAX_VIEWS]

    for v in views:
        if len(locations) > 0 and v.id == view.id:
            view_words = v.extract_completions(prefix, locations[0])
        else:
            view_words = v.extract_completions(prefix)
        view_words = filter_words(view_words)
        view_words = fix_truncation(v, view_words)
        words += [(w, v) for w in view_words]

    words = without_duplicates(words)

    for API_Keyword in pleasurazy.api:
      # If completion active
      if (pleasurazy.API_Setup and pleasurazy.API_Setup.get(API_Keyword)) or (pleasurazy.settings.get('completion_active_extend_list') and pleasurazy.settings.get('completion_active_extend_list').get(API_Keyword)):
        scope = pleasurazy.api[API_Keyword].get('scope')
        if scope and view.match_selector(locations[0], scope):
          self.completions += pleasurazy.api[API_Keyword].get('completions')

    for w, v in words:
        trigger = w
        contents = w.replace('$', '\\$')
        if v.id != view.id and v.file_name():
            trigger += '\t(%s)' % basename(v.file_name())
        if v.id == view.id:
            trigger += settings.get("file_view_abbrev", '\tview')
            ##REMOVED FOR NOW##
        #self.completions.append([trigger, contents])

    if not self.completions:
      return []

    # extend word-completions to auto-completions
    compDefault = [view.extract_completions(prefix)]
    compDefault = [(item, item) for sublist in compDefault for item in sublist if len(item) > 3]
    compDefault = list(set(compDefault))
    completions = list(self.completions)
    completions = [tuple(attr) for attr in self.completions]
    completions.extend(compDefault)
    return (completions)

# keeps first instance of every word and retains the original order, O(n)
def without_duplicates(words):
    result = []
    used_words = set()
    for w, v in words:
        if w not in used_words:
            used_words.add(w)
            result.append((w, v))
    return result

def is_excluded(scope, excluded_scopes):
    for excluded_scope in excluded_scopes:
        if excluded_scope in scope:
            return True
    return False

def filter_words(words):
    MIN_WORD_SIZE = settings.get("min_word_size", 3)
    MAX_WORD_SIZE = settings.get("max_word_size", 50)
    return [w for w in words if MIN_WORD_SIZE <= len(w) <= MAX_WORD_SIZE][0:MAX_WORDS_PER_VIEW]
# Ugly workaround for truncation bug in Sublime when using view.extract_completions()
# in some types of files.
def fix_truncation(view, words):
    fixed_words = []
    start_time = time.time()

    for i, w in enumerate(words):
        #The word is truncated if and only if it cannot be found with a word boundary before and after

        # this fails to match strings with trailing non-alpha chars, like
        # 'foo?' or 'bar!', which are common for instance in Ruby.
        match = view.find(r'\b' + re.escape(w) + r'\b', 0)
        truncated = is_empty_match(match)
        if truncated:
            #Truncation is always by a single character, so we extend the word by one word character before a word boundary
            extended_words = []
            view.find_all(r'\b' + re.escape(w) + r'\w\b', 0, "$0", extended_words)
            if len(extended_words) > 0:
                fixed_words += extended_words
            else:
                # to compensate for the missing match problem mentioned above, just
                # use the old word if we didn't find any extended matches
                fixed_words.append(w)
        else:
            #Pass through non-truncated words
            fixed_words.append(w)

        # if too much time is spent in here, bail out,
        # and don't bother fixing the remaining words
        if time.time() - start_time > MAX_FIX_TIME_SECS_PER_VIEW:
            return fixed_words + words[i+1:]

    return fixed_words

if sublime.version() >= '3000':
    def is_empty_match(match):
        return match.empty()
else:
    plugin_loaded()
    def is_empty_match(match):
        return match is None