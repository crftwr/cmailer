
cmailer_appname = u"CraftMailer"
cmailer_dirname = u"CraftMailer"
cmailer_version = "1.00"

_startup_string_fmt = u"""\
%s version %s:
  http://sites.google.com/site/craftware/
"""

def startupString():
    return _startup_string_fmt % ( cmailer_appname, cmailer_version )
