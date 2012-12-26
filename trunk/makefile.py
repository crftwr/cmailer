import os
import sys
import subprocess
import shutil
import zipfile
import md5

DIST_DIR = "dist/cmailer"
DIST_SRC_DIR = "dist/src"

PYTHON_DIR = "c:/python27"
PYTHON = PYTHON_DIR + "/python.exe"
SVN_DIR = "c:/Program Files/TortoiseSVN/bin"
DOXYGEN_DIR = "c:/Program Files/doxygen"
NSIS_DIR = "c:/Program Files (x86)/NSIS"

def unlink(filename):
    try:
        os.unlink(filename)
    except OSError:
        pass

def makedirs(dirname):
    try:
        os.makedirs(dirname)
    except OSError:
        pass

def rmtree(dirname):
    try:
        shutil.rmtree(dirname)
    except OSError:
        pass

def createZip( zip_filename, items ):
    z = zipfile.ZipFile( zip_filename, "w", zipfile.ZIP_DEFLATED, True )
    for item in items:
        if os.path.isdir(item):
            for root, dirs, files in os.walk(item):
                for f in files:
                    f = os.path.join(root,f)
                    print f
                    z.write(f)
        else:
            print item
            z.write(item)
    z.close()

def printMd5( filename ):

    fd = open(filename,"rb")
    m = md5.new()
    while 1:
        data = fd.read( 1024 * 1024 )
        if not data: break
        m.update(data)
    fd.close()
    print ""
    print filename, ":", m.hexdigest()


DIST_FILES = [
    "cmailer/cmailer.exe",
    "cmailer/lib",
    "cmailer/python27.dll",
    "cmailer/_config.py",
    "cmailer/readme.txt",
    "cmailer/theme/black",
    "cmailer/theme/white",
    "cmailer/license",
    "cmailer/doc",
    "cmailer/src.zip",
    "cmailer/dict/.keepme",
    "cmailer/extension/.keepme",
    ]

def all():
    doc()
    exe()
    installer()
    printMd5("dist/cmailer_000.exe")

def exe():
    subprocess.call( [ PYTHON, "setup.py", "py2exe", "--dist-dir", DIST_DIR ] )
    unlink( DIST_DIR + "/w9xpopen.exe" )
    unlink( DIST_DIR + "/lib/API-MS-Win-Core-LocalRegistry-L1-1-0.dll" )
    unlink( DIST_DIR + "/lib/MPR.DLL" )
    unlink( DIST_DIR + "/lib/MSIMG32.DLL" )
    unlink( DIST_DIR + "/lib/MSVFW32.DLL" )
    shutil.copy( "_config.py", DIST_DIR )
    shutil.copy( "readme.txt", DIST_DIR )
    rmtree( DIST_DIR + "/theme" )
    shutil.copytree( "theme", DIST_DIR + "/theme", ignore=shutil.ignore_patterns((".svn")) )
    rmtree( DIST_DIR + "/license" )
    shutil.copytree( "license", DIST_DIR + "/license", ignore=shutil.ignore_patterns((".svn")) )
    rmtree( DIST_DIR + "/doc" )
    shutil.copytree( "doc/html", DIST_DIR + "/doc", ignore=shutil.ignore_patterns((".svn")) )
    makedirs( DIST_DIR + "/dict" )
    shutil.copy( "dict/.keepme", DIST_DIR + "/dict" )
    makedirs( DIST_DIR + "/extension" )
    shutil.copy( "extension/.keepme", DIST_DIR + "/extension" )

    rmtree( DIST_SRC_DIR )
    makedirs( DIST_SRC_DIR )
    os.chdir(DIST_SRC_DIR)
    subprocess.call( [ SVN_DIR + "/svn.exe", "export", "--force", "../../../ckit" ] )
    subprocess.call( [ SVN_DIR + "/svn.exe", "export", "--force", "../../../cmailer" ] )
    createZip( "../cmailer/src.zip", [ "ckit", "cmailer" ] )
    os.chdir("../..")

def clean():
    rmtree("dist")
    rmtree("build")
    rmtree("doc/html")
    unlink( "tags" )

def doc():
    rmtree( "doc/html" )
    makedirs( "doc/html" )
    subprocess.call( [ DOXYGEN_DIR + "/bin/doxygen.exe", "doc/doxyfile" ] )
    subprocess.call( [ PYTHON, "tool/rst2html_pygments.py", "--stylesheet=tool/rst2html_pygments.css", "doc/index.txt", "doc/html/index.html" ] )
    subprocess.call( [ PYTHON, "tool/rst2html_pygments.py", "--stylesheet=tool/rst2html_pygments.css", "doc/changes.txt", "doc/html/changes.html" ] )
    shutil.copytree( "doc/image", "doc/html/image", ignore=shutil.ignore_patterns(".svn","*.pdn") )

def archive():
    os.chdir("dist")
    createZip( "cmailer_000.zip", DIST_FILES )
    os.chdir("..")

def installer():

    topdir = DIST_DIR

    if 1:
        fd_instfiles = open("instfiles.nsh", "w")

        for location, dirs, files in os.walk(topdir):
        
            assert( location.startswith(topdir) )
            location2 = location[ len(topdir) + 1 : ]
        
            fd_instfiles.write( "  SetOutPath $INSTDIR\\%s\n" % location2 )
            fd_instfiles.write( "\n" )
        
            for f in files:
                fd_instfiles.write( "    File %s\n" % os.path.join(location,f) )

            fd_instfiles.write( "\n\n" )

        fd_instfiles.close()

    if 1:
        fd_uninstfiles = open("uninstfiles.nsh", "w")

        for location, dirs, files in os.walk(topdir,topdown=False):
        
            assert( location.startswith(topdir) )
            location2 = location[ len(topdir) + 1 : ]
        
            for f in files:
                fd_uninstfiles.write( "  Delete $INSTDIR\\%s\n" % os.path.join(location2,f) )

            fd_uninstfiles.write( "  RMDir $INSTDIR\\%s\n" % location2 )
            fd_uninstfiles.write( "\n" )

        fd_uninstfiles.close()

    subprocess.call( [ NSIS_DIR + "/makensis.exe", "installer.nsi" ] )


def run():
    subprocess.call( [ PYTHON, "cmailer_main.py" ] )

def debug():
    subprocess.call( [ PYTHON, "cmailer_main.py", "-d" ] )

def profile():
    subprocess.call( [ PYTHON, "cmailer_main.py", "-d", "-p" ] )

if len(sys.argv)<=1:
    target = "all"
else:
    target = sys.argv[1]

eval( target + "()" )

