import ckit

cmailer_appname = u"CraftMailer"
cmailer_dirname = u"CraftMailer"
cmailer_version = "1.00"

_startup_string_fmt = u"""\
%s version %s:
  http://sites.google.com/site/craftware/
"""

def startupString():
    return _startup_string_fmt % ( cmailer_appname, cmailer_version )


strings_ja = {
    "common_yes"        : u"はい",
    "common_no"         : u"いいえ",
    "common_done"       : u'完了.',
    "common_aborted"    : u'中断しました.',
    "common_failed"     : u'失敗.',
}

strings_en = {
    "common_yes"        : u"Yes",
    "common_no"         : u"No",
    "common_done"       : u'Done.',
    "common_aborted"    : u'Aborted.',
    "common_failed"     : u'Failed.',
}

ckit.strings_ja.update(strings_ja)
ckit.strings_en.update(strings_en)

def setLocale(locale):
    ckit.setLocale(locale)

