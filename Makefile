# Usage: put the Kaggle CSV in data/, then run `make`
CSV=data/Cleaned_Indian_Food_Dataset.csv
all: index.html
build/data.json: $(CSV) scripts/prep.py
	python3 -I scripts/prep.py $(CSV) build
index.html: build/data.json src/engine.js src/template.html scripts/build.py
	python3 -I scripts/build.py build/data.json src/engine.js src/template.html index.html
test: build/data.json
	node tests/test_engine.js build/data.json 60 40
.PHONY: all test
