from pathlib import Path
ROOT=Path(__file__).parents[1]

def test_required_files():
    for name in ['requirements.txt','.env.example','render.yaml','README.md','.gitignore']:
        assert (ROOT/name).exists()

def test_no_env_file():
    assert not (ROOT/'.env').exists()
