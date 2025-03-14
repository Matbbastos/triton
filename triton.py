import logging
import subprocess
import time
from argparse import ArgumentParser
from pathlib import Path
from statistics import mean

from agents.automators import NetunoAutomator
from agents.exporter import Exporter
from agents.parsers import FileNameParser, ResultParser
from agents.validators import CommandLineArgsValidator
from globals.constants import INITIAL_DATES, NETUNO_STARTUP_WAIT_TIME, SIMULATION_PARAMETERS
from globals.errors import (
    InvalidNetunoExecutableError, InvalidSourceDirectoryError, MissingInputDataError)

logger = logging.getLogger("triton")


def run_netuno(
        path_to_netuno: Path,
        wait_after_start: int = NETUNO_STARTUP_WAIT_TIME) -> subprocess.Popen:
    """
    Executes the Netuno application in a new process, returning the corresponding Popen
    object.

    Args:
        path_to_netuno (Path): Path to the Netuno executable file.
        wait_after_start (int): Time, in seconds, to wait after initializing Netuno before
        returning. Defaults to `globals.constants.NETUNO_STARTUP_WAIT_TIME`.

    Returns:
        subprocess.Popen: New Popen instance corresponding to the process executing Netuno.
    """
    new_process = subprocess.Popen(args=(path_to_netuno,))
    logger.debug(f"Successfully spawned new process #{new_process.pid} with Netuno 4")
    time.sleep(wait_after_start)
    return new_process


def setup_logger(
        logger: logging.Logger, quiet_count: int = 0, verbose: bool = False) -> None:
    """
    Configures a logger for the application, defining output format and log level according
    to quiet or verbose arguments.

    Args:
        logger (logging.Logger): Logger channel to be configured.
        quiet_count (int): Number of times the 'quiet' flag was provided. Defaults to 0.
        verbose (bool): Whether the 'verbose' flag was provided. Defaults to False.
    """
    if verbose:
        log_level = logging.DEBUG
    elif quiet_count == 1:
        log_level = logging.WARNING
    elif quiet_count >= 2:
        log_level = logging.ERROR
    else:
        log_level = logging.INFO

    logger.propagate = True
    logger.setLevel(log_level)

    formatter = logging.Formatter(
        fmt="%(asctime)s  %(levelname)-8.8s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z")
    handler = logging.StreamHandler()
    handler.setLevel(log_level)
    handler.setFormatter(formatter)
    logger.addHandler(handler)


def main(args: CommandLineArgsValidator):
    global_start_time = time.perf_counter()

    netuno_process = run_netuno(args.netuno_exe_path)
    automator = NetunoAutomator()
    durations = []

    exporter = Exporter(args.precipitation_dir_path.parent.parent)
    path_iterator = args.precipitation_dir_path.iterdir()
    iteration_start_time = time.perf_counter()
    first_file = next(path_iterator)
    city, model, scenario = FileNameParser.get_metadata(first_file)
    output_path = automator.run_first_simulation(
        first_file, INITIAL_DATES[scenario], **SIMULATION_PARAMETERS)
    parser = ResultParser(output_path)
    exporter.save_results(city, model, scenario, parser.parse_results())
    logger.info(
        f"Finished configuration and first simulation ({city}, {model}, {scenario}) in "
        f"{time.perf_counter() - iteration_start_time:.2f}s")
    for file in path_iterator:
        iteration_start_time = time.perf_counter()
        city, model, scenario = FileNameParser.get_metadata(file)
        output_path = automator.run_simulation(file, INITIAL_DATES[scenario])
        parser = ResultParser(output_path)
        exporter.save_results(city, model, scenario, parser.parse_results())

        duration = time.perf_counter() - iteration_start_time
        durations.append(duration)
        logger.info(
            f"Finished simulation for ({city}, {model}, {scenario}) in {duration:.2f}s")

    logger.info(
        f"Completed all operations in {time.perf_counter() - global_start_time:.2f}. "
        f"Average time per iteration: {mean(durations)}s")

    netuno_process.terminate()
    logger.info("Successfully terminated Netuno process")


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument(
        "netuno_exe_path", metavar="path/to/netuno.exe", type=Path,
        help="path to a Netuno executable file")
    parser.add_argument(
        "precipitation_dir_path", metavar="path/to/precipitation", type=Path,
        help=(
            "path to a directory containing the input precipitation data files, in CSV "
            "format"))
    parser.add_argument(
        "-q", "--quiet", action="count", default=0,
        help="turn on quiet mode (cumulative), which hides log entries of levels lower "
        "than WARNING, then ERROR. Ignored if --verbose is present")
    parser.add_argument(
        "-v", "--verbose", action="store_true", default=False, help=(
            "turn on verbose mode, to display all log messages of level DEBUG and above. "
            "Overrides --quiet"))

    validator = CommandLineArgsValidator()
    parser.parse_args(namespace=validator)
    setup_logger(logger, validator.quiet, validator.verbose)

    try:
        validator.validate_arguments()
    except (
            InvalidNetunoExecutableError,
            InvalidSourceDirectoryError,
            MissingInputDataError) as exception:
        logger.exception(f"Command line arguments validation failed. Details:\n{exception}")
    else:
        main(validator)
