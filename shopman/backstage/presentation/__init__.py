"""Backstage presentation layer — appearance shaping for operator surfaces.

Where ``projections/`` answers *what is the data* (reading the Core), this package
answers *how does a fragment look*: labels, tone, copy, and the ``data-*`` contract
the touch clients (POS, KDS) read back. Views own transport (status codes, HX
triggers); these view-models own presentation. See adr-014.
"""
