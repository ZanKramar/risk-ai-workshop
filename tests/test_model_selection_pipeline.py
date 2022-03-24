from pathlib import Path
import shutil
import subprocess
import csv
from itertools import product

import pytest
import pandas as pd

import risk_learning.model_selection
from risk_learning.model_selection import utils, split

PROJECT_ROOT = Path(__file__).parent.parent
MODEL_SELECTION_DIR = Path(risk_learning.model_selection.__file__).parent


def test_pipeline_runs(tmpdir, monkeypatch):
    '''Weak end-to-end test'''

    # Test setup
    params = utils.get_params()  # Violate Uncle Bob "locate where used" due to env var monkeypatch below  # noqa: E501

    tmpdir = Path(tmpdir)
    data_dir_test = tmpdir / 'notebooks' / 'data'
    data_dir_test.mkdir(parents=True)

    shutil.copy(
        src=PROJECT_ROOT / 'notebooks' / 'data' / 'default.csv',
        dst=data_dir_test
    )
    monkeypatch.setenv('PROJECT_ROOT', tmpdir.as_posix())

    # Split stage
    in_path = data_dir_test / 'default.csv'
    split_out = subprocess.run([
        'python', 'split.py',
        '--data_path', in_path.as_posix()
    ], cwd=MODEL_SELECTION_DIR, check=True)

    # Test that script ran without error
    assert split_out.returncode == 0

    # Test number of output data files
    stage_name = 'split'
    out_file_paths = list((data_dir_test / stage_name).glob('*'))
    assert len(out_file_paths) == 3 * 2  # = number of splits * data sets per split  # noqa: E501

    # Test shape of output data
    with open(in_path, 'r') as fp:
        input_data_file = csv.reader(fp)
        row_count = sum(1 for row in input_data_file)

    input_data_n_records = row_count - 1
    stage_params = params[stage_name]
    expected_n_records = [
        round(input_data_n_records * stage_params['train_ratio']),
        round(input_data_n_records * stage_params['test_ratio']),
        round(
            input_data_n_records
            * (1 - stage_params['train_ratio'] - stage_params['test_ratio'])
        )
    ]

    expected_n_fields = [len(stage_params['non_target_cols']), 1]  # [n-non-target, n-target]  # noqa: E501
    expected_shapes = frozenset(product(expected_n_records, expected_n_fields))

    actual_shapes = []
    for out_path in out_file_paths:
        df = pd.read_csv(out_path)
        actual_shapes.append(df.shape)

    assert frozenset(actual_shapes) == expected_shapes

    # Model selection stage
    stage_name = 'fit'
    stage_params = params[stage_name]

    fit_out = subprocess.run([
        'python', 'fit.py',
        '--input_data_stage', 'split',
        '--feature_filename', 'X-train.csv',
        '--target_filename', 'y-train.csv'
    ], cwd=MODEL_SELECTION_DIR, check=True)

    # Test that script ran without error
    assert fit_out.returncode == 0

    out_file_paths = list((data_dir_test / stage_name).glob('*'))

    assert len(out_file_paths) == 1  # TODO change


# Test model selection utils
def test_get_params():
    '''Weak test for shared function to read model selection parameters'''
    params = utils.get_params()
    assert isinstance(params, dict)


# Test split script
@pytest.mark.parametrize(
    'train_ratio,test_ratio,ExpectedException',
    [
        (0.6, 0.2, None),
        (0.9, 0.9, ValueError),
        (-0.5, 0.8, ValueError),
        (0.5, -0.3, ValueError),
    ]
)
def test_get_validation_ratio_split(
    train_ratio, test_ratio, ExpectedException
):
    if ExpectedException is None:
        split.validate_split_ratios(train_ratio, test_ratio)
    else:
        with pytest.raises(ExpectedException):
            split.validate_split_ratios(train_ratio, test_ratio)
