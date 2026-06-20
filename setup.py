from setuptools import setup, find_packages

setup(
    name="mt5bt",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "click>=8.1.0",
        "PyYAML>=6.0",
        "MetaTrader5>=5.0.45",
        "pandas>=2.0.0",
        "matplotlib>=3.7.0",
        "jinja2>=3.1.0",
        "lxml>=4.9.0",
        "colorama>=0.4.6",
        "tabulate>=0.9.0",
        "numpy>=1.24.0",
    ],
    entry_points={
        "console_scripts": [
            "mt5bt=mt5bt.cli:cli",
        ],
    },
    python_requires=">=3.9",
)
