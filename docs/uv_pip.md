
## pip
# From project root on laptop
uv export -o requirements.txt
# or, if you want the new PEP 751 style:
uv export -o pylock.toml

#then with pip:
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
python3 -m venv .venv
