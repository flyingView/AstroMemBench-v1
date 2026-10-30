"""The fixed alphabetical report interface used by the E3 location tasks."""


def location(number):
    return f'N{number:02d}'


def report_options():
    return [{'action':'select','option':letter,'operation':{'kind':'report','location':location(n)},
             'description':f'报告当前位置为{location(n)}。'} for n,letter in enumerate('ABCDEFGHI',1)] + [
        {'action':'select','option':'J','operation':{'kind':'report','location':None},'description':'报告无法确定。'}]


def report_command(name):
    return {'action':'select','option':'ABCDEFGHI'[int(name[1:])-1]}
