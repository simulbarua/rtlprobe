"""Original Icarus execution, with unchanged commands and result records."""
from ..evidence import treehashes, filehash, save
from ..oracle import classify


def build(runner, config, name, source):
    binary = runner.out/(name+".vvp")
    runner.require(name+"_compile", ["iverilog", *config["compile_flags"], "-s", config["test_top"],
                   "-o", binary, *config["rtl"], config["testbench"]], source, config["limits"]["compile_seconds"])
    return binary


def run(runner, config, name, source, binary):
    hashes = treehashes(source)
    executable = filehash(binary)
    cwd = simulation_cwd(config, runner.out, name, source)
    if cwd != source:
        cwd.mkdir(parents=True, exist_ok=False)
    run = runner.run(name, ["vvp", "-N", binary], cwd, config["limits"]["simulation_seconds"])
    result = classify((runner.out/run["stdout"]).read_text(), (runner.out/run["stderr"]).read_text(),
                      run["returncode"], run["timed_out"], config=config)
    if hashes != treehashes(source) or executable != filehash(binary):
        raise ValueError("Source or executable changed during simulation")
    result.update(run_id=name, source_hashes=hashes, executable_sha256=executable,
                  test_id=config["test_id"], seed=config["seed"])
    save(runner.out/(name+".json"), result)
    return result


def simulation_cwd(config, output, name, source):
    # The upstream AES bench writes a VCD in cwd. Keep all three dumps separate
    # from their immutable original, control and restored source snapshots.
    return output/'waveforms'/name if config.get('target_id') == 'aes' else source

