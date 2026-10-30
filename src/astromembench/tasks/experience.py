"""Public, timestamped trial archives with neutral job-linked observations."""
import re

from .prose import paragraphs


def record_trial(history,at,*,job,condition,method,started_s,finished_s,result,description,result_text,layout):
    """Archive a real completed trial; splitting never changes the occurrence clocks."""
    start = {'job':job,'condition':condition,'method':method,'started_s':started_s}
    finish = {'job':job,'finished_s':finished_s,'result':result}
    if layout == 'combined':
        history.add(at,f'{job}：{description}；{result_text}',occurred=finished_s,event='experience_trial',**start,
                    finished_s=finished_s,result=result)
    else:
        history.add(at-1 if layout == 'previous_round' else at,f'{job}开始：{description}。',
                    occurred=started_s,event='experience_trial_started',**start)
        history.add(at,f'{job}完成验收：{result_text}',occurred=finished_s,event='experience_trial_completed',**finish)


def reconstruct_trials(history, read_description, read_result):
    """Join only explicit job identities, independently of receipt adjacency or order."""
    starts,finishes = {},{}
    for text in paragraphs(history):
        record = re.fullmatch(r'(J\d+)(开始：|完成验收：|：)(.+)',text)
        if not record:
            continue
        job,kind,body = record.groups()
        if kind == '：':
            description,result = body.split('；',1)
            starts[job] = {'job':job,**read_description(description)}
            finishes[job] = {'job':job,**read_result(result)}
        elif kind == '开始：':
            starts[job] = {'job':job,**read_description(body.removesuffix('。'))}
        else:
            finishes[job] = {'job':job,**read_result(body)}
    if starts.keys() != finishes.keys():
        raise ValueError('Historical trial conditions and results must have matching job identities')
    rows = [{**start,**finishes[job]} for job,start in starts.items()]
    if any(r['finished_s'] < r['started_s'] for r in rows):
        raise ValueError('Historical trial cannot finish before starting')
    return sorted(rows,key=lambda r:(r['started_s'],r['job']))
