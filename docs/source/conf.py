# Configuration file for the Sphinx documentation builder.
#
# This file only contains a selection of the most common options. For a full
# list see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Path setup --------------------------------------------------------------

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
#
import os
import sys
sys.path.insert(0, os.path.abspath('../..'))
sys.setrecursionlimit(1500)

# -- Project information -----------------------------------------------------

project = 'Quetz'
copyright = '2020, QuantStack'
author = 'QuantStack'

autosummary_generate = True
autodoc_typehints = "none"

import quetz

version = str(quetz.__version__)
release = version

# -- General configuration ---------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = ['sphinx.ext.autodoc',
              'numpydoc',
              "sphinx.ext.autosummary",
              'sphinx.ext.napoleon',
              'm2r2']

# Add any paths that contain templates here, relative to this directory.
templates_path = ['./_templates']

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = []

napoleon_include_init_with_doc = True

# -- Options for HTML output -------------------------------------------------

html_logo = '../assets/quetz_doc.png'

html_theme = "pydata_sphinx_theme"

# The name of the Pygments (syntax highlighting) style to use.
pygments_style = "tango"

html_theme_options = {
    "external_links": [],
    "github_url": "https://github.com/TheSnakePit/quetz",
    "show_prev_next": False
}


# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ['_static']

html_css_files = [
    "css/default.css"
]
