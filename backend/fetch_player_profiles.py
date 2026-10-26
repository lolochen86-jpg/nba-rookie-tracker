#!/usr/bin/env python3
"""Separate detailed player data; never modifies the leaderboard snapshot."""
import json, math
from pathlib import Path
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from nba_api.stats.endpoints import leaguedashplayerstats, leaguegamelog
ROOT=Path(__file__).resolve().parents[1]
SEASON='2026-27'
COUNT_KEYS=['PTS','OREB','DREB','REB','AST','TOV','STL','BLK','BLKA','PF','PFD','FGM','FGA','FG3M','FG3A','FTM','FTA','PLUS_MINUS']
def clean(v):
    if isinstance(v,dict):return {k:clean(x) for k,x in v.items() if not k.endswith('_RANK')}
    if isinstance(v,list):return [clean(x) for x in v]
    if hasattr(v,'item'):v=v.item()
    if isinstance(v,float) and not math.isfinite(v):return None
    return v

def request(kind):
    if kind=='games':
        ep=leaguegamelog.LeagueGameLog(player_or_team_abbreviation='P',season=SEASON,season_type_all_star='Regular Season',direction='DESC',timeout=35)
    else:
        mode,measure=kind.split(':')
        ep=leaguedashplayerstats.LeagueDashPlayerStats(season=SEASON,season_type_all_star='Regular Season',per_mode_detailed=mode,measure_type_detailed_defense=measure,timeout=35)
    rows=ep.get_data_frames()[0].to_dict('records')
    if not rows:raise ValueError('Empty official response')
    return clean(rows)

def aggregate(games):
    if not games:return None
    n=len(games);s={'GP':n,'W':sum(g.get('WL')=='W' for g in games)};s['L']=n-s['W']
    for k in ['MIN']+COUNT_KEYS:s[k]=sum(float(g.get(k) or 0) for g in games)/n
    for made,attempt,key in [('FGM','FGA','FG_PCT'),('FG3M','FG3A','FG3_PCT'),('FTM','FTA','FT_PCT')]:s[key]=s[made]/s[attempt] if s[attempt] else None
    s['TS_PCT']=s['PTS']/(2*(s['FGA']+.44*s['FTA'])) if s['FGA']+.44*s['FTA'] else None
    s['EFG_PCT']=(s['FGM']+.5*s['FG3M'])/s['FGA'] if s['FGA'] else None
    s['AST_TOV']=s['AST']/s['TOV'] if s['TOV'] else None
    return s

def main():
    roster=json.loads((ROOT/'data/rookies_latest.json').read_text())
    people={str(p['nbaPersonId']):p for p in roster['class2025']+roster['class2026']}
    target=ROOT/'data/player_profiles.json'
    previous=json.loads(target.read_text()) if target.exists() else {'players':{}}
    players=previous.get('players',{})
    now=datetime.now(timezone(timedelta(hours=8))).isoformat()
    kinds=['PerGame:Base','Totals:Base','PerGame:Advanced','PerGame:Misc','PerGame:Scoring','PerGame:Usage','games']
    results={};errors={}
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures={pool.submit(request,k):k for k in kinds}
        for f in as_completed(futures):
            k=futures[f]
            try:results[k]=f.result();print('Fetched',k,len(results[k]),flush=True)
            except Exception as exc:errors[k]=str(exc);print('Unavailable',k,type(exc).__name__,flush=True)
    for pid in people:players.setdefault(pid,{'sections':{}})
    for kind,rows in results.items():
        if kind=='games':continue
        for row in rows:
            pid=str(int(row['PLAYER_ID']))
            if pid in people:players[pid]['sections'][kind]={'updatedAt':now,'data':row}
    if 'games' in results:
        grouped={pid:{} for pid in people}
        for row in results['games']:
            pid=str(int(row['PLAYER_ID']))
            if pid in grouped:grouped[pid][str(row['GAME_ID'])]=row
        for pid,unique in grouped.items():
            games=sorted(unique.values(),key=lambda g:(g.get('GAME_DATE',''),str(g['GAME_ID'])),reverse=True)
            if not games:continue
            sections=players[pid]['sections']
            sections['games']={'updatedAt':now,'data':games}
            sections['recent']={'updatedAt':now,'data':{'last5':aggregate(games[:5]),'last10':aggregate(games[:10])}}
            sections['splits']={'updatedAt':now,'data':{label:aggregate([g for g in games if predicate(g)]) for label,predicate in [('home',lambda g:'vs.' in g.get('MATCHUP','')),('away',lambda g:'@' in g.get('MATCHUP','')),('wins',lambda g:g.get('WL')=='W'),('losses',lambda g:g.get('WL')=='L')]}}
    payload={'season':SEASON,'source':'NBA Stats','attemptedAt':now,'errors':list(errors),'players':players}
    target.parent.mkdir(exist_ok=True);temp=target.with_suffix('.tmp');temp.write_text(json.dumps(payload,ensure_ascii=False,allow_nan=False,separators=(',',':')));temp.replace(target)
    print('Saved profiles; categories updated:',len(results),flush=True)
if __name__=='__main__':main()
