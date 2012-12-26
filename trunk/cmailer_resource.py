
cfiler_appname = u"内骨格"
cfiler_dirname = u"CraftFiler"
cfiler_version = "2.20"

_startup_string_fmt = u"""\
%s version %s:
  http://sites.google.com/site/craftware/
"""

def startupString():
    return _startup_string_fmt % ( cfiler_appname, cfiler_version )
