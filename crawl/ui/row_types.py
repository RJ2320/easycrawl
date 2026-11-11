"""Readable spreadsheet row categories derived from the actual parsed crawl."""
from ..model import Header, RolePair, ListBlock, Legal, LogoRow


def describe_rows(crawl, project, count):
    result = [{'label':'', 'description':'Blank / spacing row', 'manual':False} for _ in range(count)]
    explicit = {row:item for item in project.overrides for row in range(item['start'],item['end']+1)}
    music = {row for item in project.music_blocks for row in range(item['start'],item['end']+1)}
    styled = {row for item in project.cell_formats for row in range(item['start'],item['end']+1)}
    for block in crawl.blocks():
        rows = [block.row-1]
        if isinstance(block,Header):
            label,description = ('Song title','Music song title') if block.level==2 else ('Heading','Section heading')
        elif isinstance(block,RolePair):
            if block.name_cells is not None or block.center_names:
                label,description = 'Names only','Names only, using the shared name style'
            elif block.music:
                label,description = 'Music','Music credits'
            elif block.role:
                label,description = 'Role / name','Role and name columns'
            else:
                label,description = 'Name','Name continuation'
        elif isinstance(block,ListBlock):
            rows = list(dict.fromkeys(block.name_row(i)-1 for i in range(len(block.names))))
            thanks = explicit.get(block.row-1,{}).get('kind')=='thanks'
            label,description = ('Thanks','Special thanks names') if thanks else ('List','Name list')
        elif isinstance(block,Legal):
            label,description = 'Legal','Legal text'
        elif isinstance(block,LogoRow):
            label,description = 'Logos','Logo block'
        else:
            continue
        for row in rows:
            if 0<=row<count:
                manual = row in explicit or row in music
                detail = description + (' — marked manually' if manual else ' — automatic')
                if row in styled:
                    detail += '\n* Manual font / text styling is applied to this row.'
                result[row] = dict(label=label+(' *' if row in styled else ''),description=detail,manual=manual)
    return result
