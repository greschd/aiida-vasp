#!/usr/bin/env runaiida
from aiida.orm import Code, Group
from aiida_vasp.calcs.maker import VaspMaker
from aiida.common.exceptions import NotExistent
import sys

usage = '''runaiida hf_wannier.py <code@comp> <cif/POSCAR file>'''


def add_to_group(node):
    try:
        g = Group.get_from_string('examples')
    except NotExistent:
        g = Group(name='examples')
        g.store()
    g.add_nodes(node)

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print(usage)
        sys.exit()
    mkr = VaspMaker(
        structure=sys.argv[2],
        calc_cls='vasp.vasp2w90',
        paw_map={'In': 'In_d', 'Sb': 'Sb'},
        paw_family='pbe'
    )
    mkr.add_settings(
        ediff=1e-5,
        lsorbit=True,
        isym=0,
        ismear=0,
        sigma=0.05,
        gga='PE',
        encut=380,
        magmom='600*0.0',
        nbands=36,
        kpar=4,
        nelmin=6,
        lwave=False,
        aexx=0.25,
        lhfcalc=True,
        hfscreen=0.23,
        algo='N',
        time=0.4,
        precfock='normal',
        lwannier90=True
    )
    mkr.set_kpoints_mesh([6, 6, 6])
    mkr.queue = 'dphys_compute_wk'
    mkr.resources['num_machines'] = 2
    mkr.resources['num_mpiprocs_per_machine'] = 18
    mkr.code = Code.get_from_string(sys.argv[1])
    mkr.label = 'hf_wannier_example'
    calc = mkr.new()
    calc.store_all()
    calc.submit()
    add_to_group(calc)
    print 'submitted hybrid Wannier90 calculation : PK = {pk}'.format(pk=calc.pk)
