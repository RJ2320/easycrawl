"""Conservative suggestions for UTF-8 text mistakenly decoded as Windows text.

Never changes source text. A reversible byte sequence is a review suggestion,
not proof that a person's name is wrong.
"""


def suggest_correction(value):
    result=[];index=0;changed=False
    while index<len(value):
        char=value[index]
        try:lead=char.encode('cp1252')[0]
        except UnicodeError:lead=0
        count=2 if 0xc2<=lead<=0xdf else 3 if 0xe0<=lead<=0xef else 4 if 0xf0<=lead<=0xf4 else 0
        if count and index+count<=len(value):
            part=value[index:index+count]
            try:
                raw=part.encode('cp1252')
                if all(0x80<=byte<=0xbf for byte in raw[1:]):
                    corrected=raw.decode('utf-8')
                    result.append(corrected);index+=count;changed=True;continue
            except UnicodeError:pass
        result.append(char);index+=1
    return ''.join(result) if changed else None
