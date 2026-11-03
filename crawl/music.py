"""Explicit song-block ranges; credit text is never rewritten."""

def blocks_from_selection(rows, selected, split=True, title=True):
    selected=sorted(set(selected))
    if not selected or selected != list(range(selected[0],selected[-1]+1)):
        raise ValueError('Select one continuous range of music rows.')
    if selected[0]<0 or selected[-1]>=len(rows):
        raise ValueError('The selected music rows are outside the sheet.')
    groups=[]; run=[]
    def flush():
        if run:
            groups.append(dict(start=run[0],end=run[-1],title=title))
            run.clear()
    for index in selected:
        b,c,d=rows[index]
        if c.strip().upper()=='MUSIC' and not b and not d:
            flush();continue
        if not any((b,c,d)):
            if split:flush()
            continue
        quoted=bool(c and not b and not d and c.startswith(('"','“',"'")))
        if split and quoted:flush()
        run.append(index)
    flush()
    if not groups:
        raise ValueError('Select at least one song with credit text, below any MUSIC heading.')
    return groups


def without_rows(items, selected):
    result=[]
    for item in items:
        run=[]
        for row in range(item['start'],item['end']+1):
            if row in selected:
                if run:
                    result.append(dict(item,start=run[0],end=run[-1]));run=[]
            else:run.append(row)
        if run:result.append(dict(item,start=run[0],end=run[-1]))
    return result
