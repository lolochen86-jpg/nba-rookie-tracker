#!/usr/bin/env python3
"""Build regular-season player data from completed ESPN box scores.
The existing cohort is the identity registry; unknown names are reported, never guessed.
"""
import json, os, re, unicodedata, urllib.request, time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict,Counter
from zh_name_mapper import CLASS_2026_BASE
ROOT=Path(__file__).resolve().parents[1]; DATA=ROOT/'data'; TZ=timezone(timedelta(hours=8))
API='https://site.api.espn.com/apis/site/v2/sports/basketball/nba/'
TEAM_MAP={'GS':'GSW','NY':'NYK','NO':'NOP','SA':'SAS','UTAH':'UTA','WSH':'WAS','PHO':'PHX'}
def get(url):
    last=None
    for _ in range(3):
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Accept':'application/json'})
            with urllib.request.urlopen(req,timeout=25) as r:return json.load(r)
        except Exception as e:last=e;time.sleep(.4)
    raise RuntimeError(f'ESPN request failed: {url}: {last}')
def norm(name):
    name=unicodedata.normalize('NFKD',name).encode('ascii','ignore').decode().lower()
    return re.sub(r'\b(jr|sr|ii|iii|iv)\b','',re.sub(r'[^a-z0-9 ]','',name)).replace(' ','')
def mean(games):
    if not games:return None
    n=len(games);out={'GP':n,'W':sum(x['WL']=='W' for x in games)};out['L']=n-out['W']
    keys=['MIN','PTS','OREB','DREB','REB','AST','TOV','STL','BLK','PF','FGM','FGA','FG3M','FG3A','FTM','FTA','PLUS_MINUS']
    for k in keys:out[k]=sum(float(x[k]) for x in games)/n
    for key,a,b in [('FG_PCT','FGM','FGA'),('FG3_PCT','FG3M','FG3A'),('FT_PCT','FTM','FTA')]:out[key]=out[a]/out[b] if out[b] else None
    out['TS_PCT']=out['PTS']/(2*(out['FGA']+.44*out['FTA'])) if out['FGA']+.44*out['FTA'] else None
    out['EFG_PCT']=(out['FGM']+.5*out['FG3M'])/out['FGA'] if out['FGA'] else None
    out['AST_TOV']=out['AST']/out['TOV'] if out['TOV'] else None
    return out
def mini(s):return dict(gp=s['GP'],mpg=round(s['MIN'],1),ppg=round(s['PTS'],1),rpg=round(s['REB'],1),apg=round(s['AST'],1),fg=round(100*(s['FG_PCT'] or 0),1),tp=round(100*(s['FG3_PCT'] or 0),1),ts=round(100*(s['TS_PCT'] or 0),1))
def scoreboard(day):
    d=get(API+'scoreboard?dates='+day.strftime('%Y%m%d')+'&limit=100')
    if 'events' not in d:raise ValueError('Invalid ESPN scoreboard')
    return [x for x in d['events'] if x['status']['type']['completed'] and x.get('season',{}).get('type')==2]
def get_game(event):
    game=get(API+'summary?event='+event['id']);groups=game.get('boxscore',{}).get('players',[])
    if len(groups)!=2:raise ValueError('Incomplete boxscore '+event['id'])
    teams=event['competitions'][0]['competitors'];scores={t['team']['abbreviation']:t for t in teams}
    out=[]
    for group in groups:
        raw_team=group['team']['abbreviation'];t=scores[raw_team];team=TEAM_MAP.get(raw_team,raw_team);op=next(x for x in teams if x['team']['abbreviation']!=raw_team);won=bool(t['winner']);home=t['homeAway']=='home'
        for block in group['statistics']:
            for row in block['athletes']:
                if row.get('didNotPlay') or not row.get('stats'):continue
                vals=dict(zip(block['names'],row['stats']));mins=vals.get('MIN','')
                if not re.match(r'^\d+(?::\d+)?$',mins):continue
                m,s=(mins.split(':')+['0'])[:2];stats={'MIN':int(m)+int(s)/60}
                for src,dst in [('PTS','PTS'),('REB','REB'),('OREB','OREB'),('DREB','DREB'),('AST','AST'),('TO','TOV'),('STL','STL'),('BLK','BLK'),('PF','PF'),('+/-','PLUS_MINUS')]:stats[dst]=float(vals[src])
                for src,a,b in [('FG','FGM','FGA'),('3PT','FG3M','FG3A'),('FT','FTM','FTA')]:stats[a],stats[b]=map(int,vals[src].split('-'))
                stats.update(GAME_ID=event['id'],GAME_DATE=datetime.fromisoformat(event['date'].replace('Z','+00:00')).astimezone(TZ).date().isoformat(),WL='W' if won else 'L',MATCHUP=team+(' vs. ' if home else ' @ ')+TEAM_MAP.get(op['team']['abbreviation'],op['team']['abbreviation']),team=team,athlete=row['athlete'])
                out.append(stats)
    if not out:raise ValueError('No valid player box scores '+event['id'])
    return out
def eligible_rookies():
    groups=get(API+'teams?limit=100')['sports'][0]['leagues'][0]['teams']
    if len(groups)!=30:raise ValueError('Incomplete ESPN team list')
    def roster(group):
        data=get(API+'teams/'+group['team']['id']+'/roster')
        if not data.get('athletes'):raise ValueError('Incomplete team roster '+group['team']['id'])
        return {'team':TEAM_MAP.get(group['team']['abbreviation'],group['team']['abbreviation']),'athletes':data['athletes']}
    with ThreadPoolExecutor(max_workers=8) as pool:all_rosters=list(pool.map(roster,groups))
    return {str(a['id']):a for group in all_rosters for a in group['athletes'] if a.get('experience',{}).get('years')==0}, all_rosters

def build_team_rosters(groups, roster, matches, now):
    known=defaultdict(list)
    for cohort,key in [('26','class2025'),('27','class2026')]:
        for p in roster[key]:known[norm(p['nameEn'])].append((cohort,p))
    appearances=Counter(str(row['athlete']['id']) for game in matches for row in game)
    seen=set();teams=[]
    for group in groups:
        members=[]
        for a in group['athletes']:
            aid=str(a['id']);candidates=known.get(norm(a['displayName']),[])
            if len(candidates)>1:raise ValueError('Ambiguous roster identity '+a['displayName'])
            if candidates:
                cohort,p=candidates[0]
                if p.get('espnId') and str(p['espnId'])!=aid:raise ValueError('Roster ESPN ID conflict')
            else:
                exp=a.get('experience',{}).get('years')
                if exp not in (0,1):continue
                cohort='27' if exp==0 else '26';p={}
            if aid in seen:raise ValueError('Duplicate ESPN team roster membership '+aid)
            seen.add(aid)
            members.append({'espnId':aid,'nbaPersonId':p.get('nbaPersonId'),'nameEn':a['displayName'],'nameZh':p.get('nameZh',a['displayName']),'year':cohort,'jersey':a.get('jersey',''),'pos':a.get('position',{}).get('abbreviation','—'),'gp':appearances[aid],'headshot':a.get('headshot',{}).get('href',''),'status':a.get('status',{}).get('type',''),'sourceUrl':'https://www.espn.com/nba/player/_/id/'+aid})
        teams.append({'team':group['team'],'players':sorted(members,key=lambda p:(p['year'],p['nameEn']))})
    if len(teams)!=30 or len({t['team'] for t in teams})!=30:raise ValueError('Invalid team roster coverage')
    return {'updatedAt':now,'source':'ESPN current team rosters','teams':teams}

def main():
    roster=json.loads((DATA/'rookies_latest.json').read_text());profiles=json.loads((DATA/'player_profiles.json').read_text());people=roster['class2025']+roster['class2026']
    registry=defaultdict(list)
    for p in people:registry[norm(p['nameEn'])].append(p)
    today=datetime.now(TZ).date();start=datetime(2026,10,20).date();days=[start+timedelta(days=i) for i in range((today-start).days+1)]
    with ThreadPoolExecutor(max_workers=8) as pool:days_results=list(pool.map(scoreboard,days))
    events={e['id']:e for batch in days_results for e in batch}
    if len(events)<10:raise ValueError('Too few completed regular-season games; keep previous data')
    cache_path=DATA/'espn_games_cache.json'
    cache=json.loads(cache_path.read_text()) if cache_path.exists() else {'season':'2026-27','games':{}}
    if cache.get('season')!='2026-27':cache={'season':'2026-27','games':{}}
    cached=cache.get('games',{})
    # Recheck recent games for corrections; refresh the full season on Mondays.
    check_after=datetime.now(timezone.utc)-timedelta(days=3)
    full_audit=datetime.now(TZ).weekday()==0
    pending=[e for e in events.values() if e['id'] not in cached or full_audit or datetime.fromisoformat(e['date'].replace('Z','+00:00'))>=check_after]
    with ThreadPoolExecutor(max_workers=8) as pool: fresh=list(pool.map(get_game,pending))
    for event,rows in zip(pending,fresh):cached[event['id']]=rows
    if any(not isinstance(cached.get(i),list) or not cached[i] for i in events):raise ValueError('Incomplete ESPN cache')
    matches=[cached[i] for i in events]
    known_new={norm(p['nameEn']):p for p in CLASS_2026_BASE}
    rookie_roster,team_rosters=eligible_rookies()
    byplayer=defaultdict(list);ids=defaultdict(set);unmatched=Counter(); newly_added={}
    for game in matches:
        for row in game:
            name=row['athlete']['displayName']; candidates=registry.get(norm(name),[])
            if len(candidates)>1:raise ValueError('Ambiguous identity '+name)
            if not candidates:
                aid=str(row['athlete']['id'])
                if aid not in rookie_roster:
                    unmatched[name]+=1;continue
                if aid not in newly_added:
                    unique_id=900000000+int(aid)
                    if any(str(p['nbaPersonId'])==str(unique_id) for p in people):raise ValueError('Synthetic ID collision')
                    p={'id':'2026_espn_'+aid,'nbaPersonId':known_new.get(norm(name),{}).get('nbaPersonId',unique_id),'espnId':aid,'nameEn':name,'nameZh':known_new.get(norm(name),{}).get('nameZh',name),'team':row['team'],'pick':known_new.get(norm(name),{}).get('pick'),'round':known_new.get(norm(name),{}).get('round'),'jersey':row['athlete'].get('jersey',''),'pos':row['athlete'].get('position',{}).get('abbreviation','—'),'headshotUrls':[row['athlete'].get('headshot',{}).get('href','')],'sourceUrl':row['athlete']['links'][0]['href']}
                    newly_added[aid]=p;roster['class2026'].append(p);people.append(p);registry[norm(name)].append(p)
                candidates=[newly_added[aid]]
            p=candidates[0];pid=str(p['nbaPersonId']);ids[pid].add(row['athlete']['id']);byplayer[pid].append(dict(row))
    if any(len(x)!=1 for x in ids.values()):raise ValueError('Player identity conflict')
    if len(byplayer)<35:raise ValueError('Insufficient player coverage; keep previous data')
    for p in people:
        prev=(p.get('curr2026') or {}).get('gp',0) if p in roster['class2025'] else p.get('gp',0)
        if prev and len(byplayer.get(str(p['nbaPersonId']),[]))<prev:raise ValueError('Previously recorded appearances missing: '+p['nameEn'])
    now=datetime.now(TZ).isoformat();out=profiles['players'];missing=[]
    for p in people:
        pid=str(p['nbaPersonId']);games=sorted(byplayer.get(pid,[]),key=lambda x:(x['GAME_DATE'],x['GAME_ID']),reverse=True)
        if not games:
            # Zero is valid only after all completed games are verified.
            if p in roster['class2025']:p['curr2026']=dict(gp=0,mpg=0,ppg=0,rpg=0,apg=0,fg=0,tp=0,ts=0);p['hasPlayed2026']=False
            else:p.update(dict(gp=0,mpg=0,ppg=0,rpg=0,apg=0,fg=0,tp=0,ts=0));p['hasPlayed']=False
            p['last5']=None;continue
        s=mean(games);last=mean(games[:5]);p['team']=games[0]['team'];p['jersey']=games[0]['athlete'].get('jersey',p.get('jersey',''))
        if p in roster['class2025']:p['curr2026']=mini(s);p['hasPlayed2026']=True
        else:p.update(mini(s));p['hasPlayed']=True
        p['last5']=mini(last);p['espnId']=games[0]['athlete']['id']
        sec=out.setdefault(pid,{'sections':{}})['sections'];base=dict(s)
        sec['PerGame:Base']={'updatedAt':now,'data':base,'source':'ESPN'}
        totals={k:(v*s['GP'] if k not in ('GP','W','L','FG_PCT','FG3_PCT','FT_PCT','TS_PCT','EFG_PCT','AST_TOV') and v is not None else v) for k,v in s.items()}
        sec['Totals:Base']={'updatedAt':now,'data':totals,'source':'ESPN'}
        for g in games:
            for k,a,b in [('FG_PCT','FGM','FGA'),('FG3_PCT','FG3M','FG3A'),('FT_PCT','FTM','FTA')]:g[k]=g[a]/g[b] if g[b] else None
            del g['athlete'];del g['team']
        sec['games']={'updatedAt':now,'data':games,'source':'ESPN'}
        sec['recent']={'updatedAt':now,'data':{'last5':mean(games[:5]),'last10':mean(games[:10])},'source':'ESPN'}
        sec['splits']={'updatedAt':now,'data':{label:mean([g for g in games if pred(g)]) for label,pred in [('home',lambda g:'vs.' in g['MATCHUP']),('away',lambda g:'@' in g['MATCHUP']),('wins',lambda g:g['WL']=='W'),('losses',lambda g:g['WL']=='L')]},'source':'ESPN'}
    roster['teamRosters']=build_team_rosters(team_rosters,roster,matches,now)
    roster.update(lastUpdated=now,source='ESPN',coverage='Completed ESPN games and ESPN rookie rosters',espnGames=len(events),class2025Count=len(roster['class2025']),class2026Count=len(roster['class2026']));profiles.update(attemptedAt=now,source='ESPN',errors=[])
    for name,obj in [('rookies_latest.json',roster),('player_profiles.json',profiles),('espn_games_cache.json',{'season':'2026-27','games':cached})]:
        temp=DATA/(name+'.tmp');temp.write_text(json.dumps(obj,ensure_ascii=False,allow_nan=False,separators=(',',':')),encoding='utf8');os.replace(temp,DATA/name)
    print('ESPN completed games',len(events),'matched players',len(byplayer),'other player names',len(unmatched))
if __name__=='__main__':main()

