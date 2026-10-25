#!/usr/bin/env python3
"""Discover every NBA rookie with a regular-season appearance, including undrafted players.
Fail closed: never publish incomplete discovery or relabel stale data as fresh.
"""
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
from nba_api.stats.endpoints import leaguedashplayerstats
from zh_name_mapper import CLASS_2025_BASE, CLASS_2026_BASE

ROOT = Path(__file__).resolve().parents[1]

def fetch(season, rookies=False, last_n=0):
    args = dict(season=season, season_type_all_star='Regular Season', per_mode_detailed='PerGame', last_n_games=last_n, timeout=60)
    if rookies:
        args['player_experience_nullable'] = 'Rookie'
    frame = leaguedashplayerstats.LeagueDashPlayerStats(**args).get_data_frames()[0]
    if frame.empty:
        raise RuntimeError(f'No official results for {season}; previous snapshot retained')
    return {int(r['PLAYER_ID']): r.to_dict() for _, r in frame.iterrows() if int(r['GP']) > 0}

def stats(r):
    if not r:
        return dict(gp=0, mpg=0, ppg=0, rpg=0, apg=0, fg=0, tp=0, ts=0)
    number = lambda k: float(r.get(k, 0) or 0)
    attempts = number('FGA') + .44 * number('FTA')
    return dict(gp=int(r['GP']), mpg=round(number('MIN'),1), ppg=round(number('PTS'),1),
                rpg=round(number('REB'),1), apg=round(number('AST'),1),
                fg=round(number('FG_PCT')*100,1), tp=round(number('FG3_PCT')*100,1),
                ts=round(number('PTS')/ (2*attempts)*100,1) if attempts else 0)

def build(first, current, catalog, year):
    known = {int(p['nbaPersonId']): p for p in catalog if p.get('nbaPersonId')}
    result=[]
    for pid, row in first.items():
        base=known.get(pid,{})
        entry=dict(id=f'{year}_nba_{pid}', nbaPersonId=pid, nameEn=row['PLAYER_NAME'],
                   nameZh=base.get('nameZh',row['PLAYER_NAME']), team=(current.get(pid) or row)['TEAM_ABBREVIATION'],
                   pick=base.get('pick',0), round=base.get('round',0), jersey=base.get('jersey',''),
                   pos=base.get('pos','—'), college=base.get('college',''), honors='',
                   sourceUrl=f'https://www.nba.com/stats/player/{pid}/traditional',
                   headshotUrls=[f'https://cdn.nba.com/headshots/nba/latest/260x190/{pid}.png'])
        if year==2025:
            entry.update(fixed2025=stats(row),curr2026=stats(current.get(pid)),hasPlayed2026=pid in current,
                         statusNote='已出賽' if pid in current else '本季尚無正式賽出場紀錄')
        else:
            entry.update(stats(row),hasPlayed=True,statusBadge=f'已出賽 ({int(row["GP"])} GP)',highlight='NBA 官方例行賽統計')
        result.append(entry)
    return result

def main():
    # Rookie eligibility, rather than draft position, includes undrafted/two-way and delayed debuts.
    first=fetch('2025-26',True)
    second=fetch('2026-27',True)
    current=fetch('2026-27')
    recent=fetch('2026-27',last_n=5)
    a=build(first,current,CLASS_2025_BASE,2025)
    b=build(second,current,CLASS_2026_BASE,2026)
    for entry in a+b:
        pid=entry['nbaPersonId']
        entry['last5']=stats(recent.get(pid)) if pid in recent else None
    payload=dict(lastUpdated=datetime.now(timezone(timedelta(hours=8))).isoformat(),season='2026-27',
                 coverage='All NBA rookies with GP > 0 in regular season',source='NBA Stats',
                 class2025Count=len(a),class2026Count=len(b),class2025=a,class2026=b)
    target=ROOT/'data/rookies_latest.json'
    temporary=target.with_suffix('.tmp')
    temporary.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    temporary.replace(target)
    print(f'Published {len(a)} and {len(b)} officially recorded rookies')

if __name__=='__main__':
    try:
        main()
    except Exception as exc:
        saved = json.loads((ROOT/'data/rookies_latest.json').read_text(encoding='utf-8'))
        if saved.get('source') != 'NBA Stats':
            raise
        print(f'Official API unavailable; deploying last verified snapshot unchanged: {exc}')
