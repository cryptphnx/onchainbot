from setuptools import setup, find_namespace_packages

setup(
    name="onchainbot",
    version="0.1.0",
    description="A mirror trading bot for Ethereum and Solana DeFi protocols.",
    packages=find_namespace_packages(include=["core", "ingestion", "exec", "src.onchainbot*"]),
    package_dir={"": "."},
    install_requires=[
        line.strip()
        for line in open("requirements.txt").read().splitlines()
        if line and not line.startswith("#")
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
)
