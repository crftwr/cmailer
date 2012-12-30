import os
import traceback

def reload( filename ):
    
    global user_namespace

    try:
        fd = file( filename, 'r' )
        fileimage = fd.read()
        user_namespace = {}
        code = compile( fileimage, os.path.basename(filename), 'exec' )
        exec code in user_namespace, user_namespace
    except:
        print u'ERROR : 設定ファイルの読み込み中にエラーが発生しました.'
        traceback.print_exc()

def call( funcname, *args ):

    global user_namespace

    try:
        func = user_namespace[funcname]
    except KeyError:
        return

    try:
        func(*args)
    except:
        print u"ERROR : 設定ファイルの実行中にエラーが発生しました."
        traceback.print_exc()

