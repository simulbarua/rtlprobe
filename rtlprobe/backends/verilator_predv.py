"""Direct build of the unchanged upstream pre_dv file list, without Linux link extras."""
from .common import fresh, finish_build, run, tool


def build(runner, config, name, source):
    work = fresh(runner, config, name, source)
    spec = config['build']
    flags = [s.replace('{source}', str(source)) for s in spec['cflags']]
    command = [tool(config), '--cc', '--exe', '--build', '-j', str(spec['jobs']),
               '--top-module', config['test_top'], '--Mdir', str(work/'obj'),
               *spec['flags'], '-CFLAGS', ' '.join(flags),
               *(str(source/p) for p in spec['file_list'])]
    return finish_build(runner, config, name, source, work, command, work)
