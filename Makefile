PYTHON ?= python3

.PHONY: test replay report native capabilities local-engine reliability-freeze reliability-report router-probe overlap-test
test:
	$(PYTHON) -m unittest discover -s spikes/tests -v

replay:
	$(PYTHON) -m spikes.lab replay --out spikes/results/local/replay.json

report:
	$(PYTHON) -m spikes.lab report --out spikes/results/local/offline-report.json

native:
	$(PYTHON) spikes/native/build.py

capabilities: native
	.build/CrackitProbe.app/Contents/MacOS/CrackitProbe --capabilities

local-engine:
	$(PYTHON) spikes/native/build_local.py

reliability-freeze:
	$(PYTHON) -m spikes.evaluation freeze

reliability-report:
	$(PYTHON) -m spikes.evaluation report

router-probe:
	$(PYTHON) -m spikes.router_probe

overlap-test:
	mkdir -p .build
	clang++ -std=c++17 -O2 spikes/native/test_overlap.cpp -o .build/overlap-test
	.build/overlap-test
