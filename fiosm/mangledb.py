'''
Created on 15.11.2012

@author: Scondo

StreetMangler with some db addition
'''
from config import psy_dsn
import psycopg2
import logging

conn=None
guess_tbl="mangle_guess"

db=None
usable=False

def InitMangle(no_guess=True):
    global conn,usable,db
    try:
        import streetmangler
        conn = psycopg2.connect(psy_dsn)
        conn.autocommit=True
        locale=streetmangler.Locale('ru_RU')
        db = streetmangler.Database(locale)

        db.Load("data/ru_RU.txt")
        #for guess in ListGuess(all_=not(no_guess)):
        #    db.Add(guess)

        usable=True
        logging.info("Mangle OK")
    except BaseException as e:
        logging.warn(e.message.decode("cp1251"))
        #raise e
        usable=False
        logging.warn("Mangle Broken")

def ListGuess(all_=False):
    """Get guess for streetmangle from sql db
    """
    cur_=conn.cursor()    
    if all_:
        cur_.execute("SELECT name FROM "+guess_tbl)
    else:
        cur_.execute("SELECT name FROM "+guess_tbl+" WHERE valid=1")
    for row in cur_.fetchall():
        yield row[0].decode('UTF-8')
        
def AddMangleGuess(name):
    if not usable:
        return
    cur_=conn.cursor()
    #Do not save twice
    cur_.execute("SELECT name FROM "+guess_tbl+" WHERE name=%s",(name,))
    if cur_.fetchone():
        return
    cur_.execute("INSERT INTO "+guess_tbl+" (name) VALUES (%s)",(name,))

if __name__=='__main__':
    conn = psycopg2.connect(psy_dsn)
    conn.autocommit=True
    cur=conn.cursor()
    cur.execute("DROP TABLE IF EXISTS "+guess_tbl)
    cur.execute("CREATE TABLE "+guess_tbl+"(name varchar,  valid  smallint);")
