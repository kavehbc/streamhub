# Build the documentation site. From the repository root: make -C readthedocs html (or: make docs)
SPHINXBUILD ?= sphinx-build
SPHINXOPTS ?= -W --keep-going
BUILDDIR = _build

.PHONY: html linkcheck clean

html: ## HTML site in _build/html
	$(SPHINXBUILD) -b html $(SPHINXOPTS) . $(BUILDDIR)/html

linkcheck: ## Check the external links
	$(SPHINXBUILD) -b linkcheck . $(BUILDDIR)/linkcheck

clean:
	$(SPHINXBUILD) -M clean . $(BUILDDIR)
