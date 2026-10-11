"""Source-row ranges for side-by-side credit groups (zero-based, inclusive)."""
from .ingest import parse
from .model import ListBlock


def group_ranges(rows, break_before=()):
    result = []
    for group in parse(rows, break_before=break_before).groups:
        last = group.blocks[-1]
        end = last.row - 1 + (len(last.names) - 1 if isinstance(last, ListBlock) else 0)
        result.append((group.first_row - 1, end))
    return result


def selection_range(rows, selected_rows, break_before=()):
    selected = sorted(set(selected_rows))
    if not selected or selected != list(range(selected[0], selected[-1] + 1)):
        raise ValueError('Select one continuous range of rows containing at least two groups.')
    groups = [(a, b) for a, b in group_ranges(rows, break_before) if b >= selected[0] and a <= selected[-1]]
    if len(groups) < 2:
        raise ValueError('Select at least two groups, separated by a blank row. Each group becomes one block.')
    return groups[0][0], groups[-1][1], len(groups)


def insert_row(arrangements, row):
    for item in arrangements:
        if row <= item['start']:
            item['start'] += 1
            item['end'] += 1
        elif row <= item['end'] + 1:
            item['end'] += 1


def delete_rows(arrangements, deleted):
    deleted = set(deleted)
    kept = []
    for item in arrangements:
        survivors = [i for i in range(item['start'], item['end'] + 1) if i not in deleted]
        if not survivors:
            continue
        item['start'] = survivors[0] - sum(i < survivors[0] for i in deleted)
        item['end'] = survivors[-1] - sum(i < survivors[-1] for i in deleted)
        kept.append(item)
    arrangements[:] = kept
