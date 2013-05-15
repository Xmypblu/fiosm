#!/usr/bin/python
# -*- coding: UTF-8 -*-

import melt
import mangledb
mangledb.InitMangle(False)
from config import *


def Subareas(elem):
    '''Calculate subareas of relation by member role 'subarea'
    return dict with names as key and osmid as values
    '''
    if elem.osmid > 0:
        #applicable only to relation i.e. negative osmid
        return {}
    else:
        osmid = elem.osmid * (-1)
    cur = elem.conn.cursor()
    cur.execute("SELECT members FROM "+prefix+slim_rel_tbl+" WHERE id=%s",(osmid,))
    mem=cur.fetchone()
    if mem==None:
        return {}
    mem=mem[0]
    mem=zip(mem[1::2],mem[::2])#osm2pgsql use sequence to represent roles
    mem=[it[1] for it in mem if it[0]=='subarea' and (it[1][0]=='r' or it[1][0]=='w')]
    #relation stored with negative osmid 
    mem=[int(it[1:])*(-1 if it[0]=='r' else 1) for it in mem]
    
    res={}
    for id_a in mem:
        #using only valid polygons i.e. processed by osm2pgsql
        cur.execute('SELECT name FROM '+prefix+poly_table+' WHERE osm_id=%s ',(id_a,))
        name=cur.fetchone()
        if name:
            res[name[0]]=id_a
    return res

def FindCandidates(pgeom,elem,tbl=prefix+poly_table,addcond=""):
    '''Get elements that may be osm representation of elem
    That items must contain part of elem's name full or formal (this will be returned)
    and lies within polygon pgeom (polygon of parent territory)
    
    return ( [(name, osmid),..],formal)
    '''
    cur = elem.conn.cursor()
    formal=True
    name='%'+elem.formalname+'%'
    if pgeom==None:
        cur.execute("SELECT name, osm_id FROM "+tbl+" WHERE lower(name) LIKE lower(%s)"+addcond,(name,))
    else:
        cur.execute("SELECT name, osm_id FROM "+tbl+" WHERE lower(name) LIKE lower(%s) AND ST_Within(way,%s)"+addcond,(name,pgeom))
    res=cur.fetchall()
    if not res:
        if elem.offname==None or elem.formalname==elem.offname:
            return (None,None)
        name='%'+elem.offname+'%'
        if pgeom==None:
            cur.execute("SELECT name, osm_id FROM "+tbl+" WHERE lower(name) LIKE lower(%s)"+addcond,(name,))
        else:
            cur.execute("SELECT name, osm_id FROM "+tbl+" WHERE lower(name) LIKE lower(%s) AND ST_Within(way,%s)"+addcond,(name,pgeom))
        res=cur.fetchall()
        if res:
            formal=False
        else:
            return (None,None)
    
    return (res,formal)


def FindMangled(pgeom, elem, tbl=prefix + ways_table, addcond=""):
    '''Get osm representation of elem using name from streetmangler
    That items must lies within polygon pgeom (polygon of parent territory)

    return (name, osmid)
    '''
    if melt.mangledb.usable:
        mangl_n = melt.mangledb.db.CheckCanonicalForm(elem.shortname + " " + elem.formalname)
        if not mangl_n:
            return
    else:
        return
    cur = elem.conn.cursor()
    if pgeom == None:
        cur.execute("SELECT name, osm_id FROM " + tbl + " WHERE lower(name) = lower(%s)" + addcond, (mangl_n,))
    else:
        cur.execute("SELECT name, osm_id FROM " + tbl + " WHERE lower(name) = lower(%s) AND ST_Within(way,%s)" + addcond, (mangl_n, pgeom))
    return cur.fetchall()


def FindAssocPlace(elem,pgeom):
    (candidates,formal)=FindCandidates(pgeom,elem,prefix+poly_table," AND building ISNULL")
    if not candidates:
        return None
    for name in elem.names(formal):
        checked=[it[1] for it in candidates if it[0].lower()==name.lower()]
        if checked:
            elem.name = name
            return checked[0]

def FindAssocStreet(elem,pgeom):
    mangled = FindMangled(pgeom, elem, prefix + ways_table, " AND highway NOTNULL")
    if mangled:
        elem.name = mangled[0][0]
        return [it[1] for it in mangled]
    (candidates,formal)=FindCandidates(pgeom,elem,prefix+ways_table," AND highway NOTNULL")
    if not candidates:
        return None
    for name in elem.names(formal):
        checked=[it[1] for it in candidates if it[0].lower()==name.lower()]
        if checked:
            mangledb.AddMangleGuess(name)
            elem.name = name
            return checked


def AssocBuild(elem, point):
    '''Search and save building association for elem
    '''
    cur = elem.conn.cursor()
    if point:
        cur.execute("""SELECT osm_id, "addr:housenumber" FROM """ + prefix + point_table + """ WHERE "addr:street"=%s AND ST_Within(way,%s)""", (elem.name, elem.geom))
    else:
        cur.execute("""SELECT osm_id, "addr:housenumber" FROM """ + prefix + poly_table + """ WHERE "addr:street"=%s AND ST_Within(way,%s)""", (elem.name, elem.geom))
    osm_h = cur.fetchall()
    if not osm_h:
        return []
    #Filtering of found is optimisation for updating and also remove POI with address
    #found_pre = set([h.onestr for h in elem.subO('found_b')])
    #osm_h = filter(lambda it: it[1] not in found_pre, osm_h)
    found = {}
    for hid, number in osm_h:
        for house in tuple(elem.subO('not found_b')):
            if house.equal_to_str(number):
                found[hid] = house.guid
                house._osmid = hid
                house._osmkind = point
    if found:
        elem.conn.autocommit = False
        for myrow in found.iteritems():
            cur.execute("INSERT INTO " + prefix + bld_aso_tbl + " (aoguid,osm_build,point) VALUES (%s, %s, %s)", (myrow[1], myrow[0], point))
        elem.conn.commit()
        elem.conn.autocommit = True


def AssociateO(elem):
    '''Search and save association for all subelements of elem
    
    This function should work for elements with partitially associated subs 
    as well as elements without associated subs 
    '''
    if not elem.kind:
        return
    AssocBuild(elem, 0)
    AssocBuild(elem, 1)
    cur = elem.conn.cursor()
    #run processing for found to parse their subs
    for sub in tuple(elem.subAO('found', False)):
        AssociateO(melt.fias_AONode(sub))
    #find new elements for street if any
    for sub in tuple(elem.subAO('street', False)):
        sub_ = melt.fias_AONode(sub)
        streets=FindAssocStreet(sub_,elem.geom)
        if streets<>None:
            elem.conn.autocommit = False
            for street in streets:
                cur.execute("SELECT osm_way FROM "+prefix+way_aso_tbl+" WHERE osm_way=%s",(street,))
                if not cur.fetchone():
                    cur.execute("INSERT INTO " +  prefix+way_aso_tbl + " (aoguid,osm_way) VALUES (%s, %s)", (sub.guid, street))
            elem.conn.commit()
            elem.conn.autocommit = True
            AssociateO(sub_)
    #search for new elements
    subareas = Subareas(elem)
    for sub in tuple(elem.subAO('not found', False)):
        sub_ = melt.fias_AONode(sub)
        adm_id=None
        if subareas:
            for name in sub_.names():
                adm_id=subareas.get(name)
                if adm_id:
                    del subareas[name]
                    break
                
        if adm_id==None:
            adm_id=FindAssocPlace(sub_,elem.geom)
        if not adm_id==None:
            cur.execute("INSERT INTO " + prefix + pl_aso_tbl + " (aoguid,osm_admin) VALUES (%s, %s)", (sub.guid, adm_id))
            elem.child_found(sub, 'found')
            sub_.osmid = adm_id
            sub_.kind = 2
            AssociateO(sub_)
        else:
            streets=FindAssocStreet(sub_,elem.geom)
            if streets<>None:
                elem.conn.autocommit = False
                for street in streets:
                    cur.execute("INSERT INTO " + prefix + way_aso_tbl + " (aoguid,osm_way) VALUES (%s, %s)", (sub.guid, street))
                elem.conn.commit()
                elem.conn.autocommit = True
                elem.child_found(sub, 'street')
                sub_.kind = 1
                sub_.osmid = streets[0]
                AssociateO(sub_)
    elem.stat('not found_r')
    elem.stat('not found_b_r')


def AssocRegion(guid):
    region = melt.fias_AONode(guid)
    if not region.kind:
        adm_id = FindAssocPlace(region, None)
        if adm_id != None:
            cur = region.conn.cursor()
            cur.execute("INSERT INTO " + prefix + pl_aso_tbl + " (aoguid,osm_admin) VALUES (%s, %s)", (guid, adm_id))
            region = melt.fias_AONode(guid, 2, adm_id)

    AssociateO(region)
    print region.name.encode('UTF-8') + str(region.kind)


def fedobj():
    conn = melt.psycopg2.connect(melt.connstr)
    cur = conn.cursor()
    cur.execute("SELECT aoguid FROM fias_addr_obj f WHERE parentguid is Null")
    return [it[0] for it in cur.fetchall()]


def AssORoot():
    '''Associate and process federal subject (they have no parent id and no parent geom)
    '''
    for sub in fedobj():
        AssocRegion(sub)


def AssORootM():
    '''Associate and process federal subject (they have no parent id and no parent geom)
    '''
    from multiprocessing import Pool
    pool = Pool()
    results = []
    for sub in fedobj():
        results.append(pool.apply_async(AssocRegion, (sub,)))

    while results:
        result = results.pop(0)
        result.get()
        print len(results)


if __name__=="__main__":
    from deploy import AssocTableReCreate, AssocBTableReCreate, StatTableReCreate, AssocIdxCreate
    AssocTableReCreate()
    AssocBTableReCreate()
#    AssocTriggersReCreate()
    StatTableReCreate()
    AssORootM()
    AssocIdxCreate()
