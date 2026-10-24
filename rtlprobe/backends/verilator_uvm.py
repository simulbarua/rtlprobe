"""FuseSoC setup-only, immutable patch recipe, fresh Verilation, native binary."""
from pathlib import Path
from . import uvm_patchset
from .common import fresh, finish_build, run, tool, fusesoc, build_environment


def build(runner, config, name, source):
    work = fresh(runner, config, name, source)
    exported = work/'export'
    fs_config = work/'fusesoc.conf'
    fs_config.write_text('[main]\ncache_root = '+str(work/'cache')+'\n')
    runner.require(name+'_setup', [fusesoc(), '--config='+str(fs_config), '--cores-root='+str(source), 'run', '--target=sim',
                   '--tool=vcs', '--setup', '--work-root='+str(exported),
                   '--mapping=lowrisc:prim_generic:all:0.1', config['build']['core']],
                   work, config['limits']['compile_seconds'], env_extra=build_environment())
    uvm_patchset.apply(exported/'src', 'opentitan', config['design'])
    uvm = uvm_patchset.unpack(work/'uvm')
    uvm_patchset.apply(uvm, 'uvm', config['design'])
    scripts = list(exported.glob('*.scr'))
    if len(scripts) != 1:
        raise ValueError('Expected exactly one FuseSoC exported VCS file list')
    converted = []
    for line in scripts[0].read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('//'):
            continue
        prefix = '+incdir+' if line.startswith('+incdir+') else ''
        path = line[len(prefix):]
        if not path.startswith('src/') or not (exported/path).resolve().is_relative_to(exported):
            raise ValueError(f'Unexpected FuseSoC file-list entry: {line}')
        converted.append(prefix+str(exported/path))
    filelist = work/'sources.f'
    filelist.write_text('\n'.join(converted)+'\n')
    compat = work/'compat'
    compat.mkdir()
    uvm_patchset.apply(compat, 'shim', config['design'])
    spec = config['build']
    command = [tool(config), '--binary', '--timing', '-j', str(spec['jobs']),
               '--top-module', config['test_top'], '--Mdir', str(work/'obj'), *spec['flags'],
               '-CFLAGS', spec.get('optimization', '-O0'), '+incdir+'+str(uvm/'src'),
               *('+define+'+d for d in config['defines']),
               str(compat/'ot_uvm_compat.svh'), str(uvm/'src/uvm_pkg.sv'), '-f', str(filelist)]
    return finish_build(runner, config, name, source, work, command, work)
