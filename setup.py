from setuptools import setup, find_packages
from jocular import __version__

import pathlib

here = pathlib.Path(__file__).parent.resolve()

long_description = (here / 'README.md').read_text(encoding='utf-8')

URL = 'https://github.com/MartinCooke/jocular'

setup(
    name='jocular',
    version=__version__,
    description='A tool for near-live observation of astronomical objects',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url=URL,
    author='Martin Cooke',
    author_email='martin.cooke.1917@gmail.com',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: End Users/Desktop',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
    ],
    keywords='astronomy',
    packages=find_packages(exclude=['tests', 'docs']),
    include_package_data=True,
    python_requires='>=3.6',
    install_requires=[
        'scikit-image>=0.18.1',  # numerous image ops (includes NumPy)
        'Click>=7.1.2',  # command line interface
        'kivy>=2.0.0',  # main GUI framework
        'astropy>=4.2',  # fits etc
        'mss>=6.1.0',  #  snapshots
        'pyusb>=1.1.1',  # camera
        'hidapi>=0.10.1',  # filterwheel
    ],
    entry_points='''
        [console_scripts]
        jocular=jocular.startjocular:startjocular
        ''',
    project_urls={
        'Bug Reports': URL + '/issues',
        'Source': URL,
    },
)
