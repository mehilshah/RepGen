from setuptools import find_packages, setup

setup(
    name="repgen",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "annoy",
        "numpy",
        "pylint",
        "rank_bm25",
        "requests",
        "scikit-learn",
        "sentence-transformers",
        "torch",
        "transformers",
        "pandas",
        "openai",
        "rich",
        "fastapi",
        "uvicorn",
        "pydantic",
    ],
    entry_points={
        "console_scripts": [
            "repgen=repgen.cli:main",
        ],
    },
    author="Mehil B. Shah",
    description="Automated Deep Learning Bug Reproduction with LLMs",
    url="https://github.com/mehilshah/RepGen",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    python_requires=">=3.8",
)
