from setuptools import setup, find_packages
from jocular import __version__

import pathlib

here = pathlib.Path(__file__).parent.resolve()

long_description = (here / 'README.md').read_text(encoding='utf-8')

URL = 'https://github.com/MartinCooke/jocular'

setup(
    name='jocular-test',
    version=__version__,
    description='A tool for near-live observation of astronomical objects',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url=URL,
    author='Martin Cooke',
    author_email='martin.cooke.1917@gmail.com',
    # For a list of valid classifiers, see https://pypi.org/classifiers/
    classifiers=[  # Optional
        'Development Status :: 4 - Beta',
        'Intended Audience :: End Users/Desktop',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
    ],
    keywords='astronomy',  # Optional
    packages=find_packages(exclude=['tests', 'docs']),
    # https://packaging.python.org/guides/distributing-packages-using-setuptools/#python-requires
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
    ],  # Optional
    # package_data={  # Optional
    #     '': ['*.json', '*.ttf', '*.dll'],
    # },
    entry_points='''
        [console_scripts]
        jocular=jocular.startjocular:startjocular
        ''',
    project_urls={  # Optional
        'Bug Reports': URL + '/issues',
        'Source': URL,
    },
)
