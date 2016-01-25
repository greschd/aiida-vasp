from aiida.orm import JobCalculation, DataFactory
from aiida.common.utils import classproperty
from aiida.common.datastructures import CalcInfo, CodeInfo


def make_use_methods(inputs):
    @classproperty
    def _use_methods(cls):
        retdict = JobCalculation._use_methods
        for inp, dct in inputs.iteritems():
            ln = dct['linkname']
            if isinstance(ln, classmethod):
                dct['linkname'] = getattr(cls, ln.__func__.__name__)
        retdict.update(inputs)
        return retdict
    return _use_methods


def make_init_internal(cls, **kwargs):
    def _update_internal_params(self):
        for k, v in kwargs.iteritems():
            setattr(self, k, v)
    return _update_internal_params


def seqify(seq_arg):
    if not isinstance(seq_arg, list) and not isinstance(seq_arg, tuple):
        seq_arg = [seq_arg]
    return tuple(seq_arg)


def datify(type_or_str):
    if isinstance(type_or_str, str):
        return DataFactory(type_or_str)
    else:
        return type_or_str


class Input(object):
    '''
    Utility class that handles mapping between CalcMeta's and Calculation's
    interfaces for defining input nodes
    '''
    def __init__(self, types, param=None, ln=None, doc=''):
        self.types = tuple(map(datify, seqify(types)))
        self.param = param
        self._ln = ln
        self.doc = doc

    def set_ln(self, value):
        if not self._ln:
            self._ln = value

    def get_dict(self):
        ret = {
            'valid_types': self.types,
            'additional_parameter': self.param,
            'linkname': self._ln,
            'docstring': self.doc
        }
        return ret

    @classmethod
    def it_filter(cls, item):
        return isinstance(item[1], Input)

    @classmethod
    def filter_classdict(cls, classdict):
        return filter(cls.it_filter, classdict.iteritems())


class IntParam(object):
    '''
    Utility class that handles mapping between CalcMeta's and Calculation's
    internal parameter interfaces
    '''

    pmap = {
        'default_parser': '_default_parser',
        'input_file_name': '_INPUT_FILE_NAME',
        'output_file_name': '_OUTPUT_FILE_NAME'
    }

    @classmethod
    def it_filter(cls, item):
        return item[0] in cls.pmap

    @classmethod
    def filter_classdict(cls, classdict):
        return filter(cls.it_filter, classdict.iteritems())

    @classmethod
    def map_param(cls, item):
        k, v = item
        return (cls.pmap[k], v)

    @classmethod
    def map_params(cls, classdict):
        return map(cls.map_param, cls.filter_classdict(classdict))

    @classmethod
    def k_filter(cls, key):
        return key in cls.pmap

    @classmethod
    def get_keylist(cls, classdict):
        return filter(cls.k_filter, classdict)


class CalcMeta(JobCalculation.__metaclass__):
    '''
    Metaclass responsible to simplify routine Calculation setup
    '''
    def __new__(cls, name, bases, classdict):
        inputs = {}
        delete = []
        inputobj = Input.filter_classdict(classdict)
        for k, v in inputobj:
            if not v.param:
                v.set_ln(k)
            else:
                v.set_ln(classdict['_get_{}_linkname'.format(k)])
            inputs[k] = v.get_dict()
            delete.append(k)
        internals = dict(IntParam.map_params(classdict))
        delete.extend(IntParam.get_keylist(classdict))
        classdict['_use_methods'] = make_use_methods(inputs)
        classdict['_update_internal_params'] = make_init_internal(
            cls, **internals)
        for k in delete:
            classdict.pop(k)
        Calc = super(CalcMeta, cls).__new__(cls, name, bases, classdict)
        return Calc


class VaspCalcBase(JobCalculation):
    __metaclass__ = CalcMeta
    input_file_name = 'INCAR'
    output_file_name = 'OUTCAR'

    def _prepare_for_submission(self, tempfolder, inputdict):
        '''
        Writes the four minimum output files,
        INCAR, POSCAR, POTCAR, KPOINTS. Delegates the
        construction and writing / copying to write_<file> methods.
        That way, subclasses can use any form of input nodes and just
        have to implement the write_xxx method accordingly.
        Subclasses can extend by calling the super method and if neccessary
        modifying it's output CalcInfo before returning it.
        '''
        # write input files
        incar = tempfolder.get_abs_path('INCAR')
        structure = tempfolder.get_abs_path('POSCAR')
        paw = tempfolder.get_abs_path('POTCAR')
        kpoints = tempfolder.get_abs_path('KPOINTS')

        self.verify_inputs(inputdict)
        self.write_incar(inputdict, incar)
        self.write_poscar(inputdict, structure)
        self.write_potcar(inputdict, paw)
        self.write_kpoints(inputdict, kpoints)

        # calcinfo
        calcinfo = CalcInfo()
        calcinfo.uuid = self.uuid
        calcinfo.retrieve_list = [
            'CHG',
            'CHGCAR',
            'CONTCAR',
            'DOSCAR',
            'EIGENVAL',
            'ELFCAR',
            'IBZKPT',
            'LOCPOT',
            'OSZICAR',
            'OUTCAR',
            'PCDAT',
            'PROCAR',
            'PROOUT',
            'STOPCAR',
            'TMPCAR',
            'WAVECAR',
            'XDATCAR',
            'vasprun.xml'
        ]
        codeinfo = CodeInfo()
        codeinfo.code_uuid = self.get_code().uuid
        codeinfo.code_pk = self.get_code().pk
        calcinfo.codes_info = [codeinfo]

        return calcinfo

    def _init_internal_params(self):
        super(VaspCalcBase, self)._init_internal_params()
        self._update_internal_params()

    def verify_inputs(self, inputdict, *args, **kwargs):
        self.check_input(inputdict, 'code')

    def check_input(self, inputdict, linkname, check_fn=lambda: True):
        notset_msg = 'input not set: %s'
        if check_fn():
            if not linkname in inputdict:
                raise ValueError(notset_msg % linkname)


    def store(self, *args, **kwargs):
        self._prestore()
        super(VaspCalcBase, self).store(*args, **kwargs)

    def _prestore(self):
        pass


# only implements gamma centered monkhorst
# no expert mode with manual basis vectors
# no fully automatic mode
# no original monkhorst (equivalent to 0.5 shift though)
kpmtemp = '''\
Automatic mesh
0
Gamma
{N[0]} {N[1]} {N[2]}
{s[0]} {s[1]} {s[2]}\
'''

# only implements direct explicit list with weights
# no cartesian
# no tetrahedron method
# no bandstructure lines
kpltemp = '''\
Explicit list
{N}
Direct
{klist}\
'''
kplitemp = '''\
{k[0]} {k[1]} {k[2]} {w}\
'''


class TentativeVaspCalc(VaspCalcBase):
    '''vasp 3.5.3 calc with nice hopefully interface'''
    incar = Input(types='parameter', doc='input parameters')
    structure = Input(types='structure', doc='aiida structure')
    paw = Input(types='vasp.potpaw', doc='paw symbols or files', param='kind')
    kpoints = Input(types='array.kpoints', doc='kpoints array or mesh')
    default_parser = 'vasp.tentative'

    def _init_internal_params(self):
        super(TentativeVaspCalc, self)._init_internal_params()
        self._update_internal_params()

    def verify_inputs(self, inputdict):
        incar = inputdict['incar'].get_dict()
        keys = map(lambda k: k.lower(), incar.keys())
        need_kp = True
        if 'kspacing' in keys and 'kgamma' in keys:
            need_kp = False
        self.use_kp = True
        kp = inputdict.get('kpoints')
        if not need_kp:
            msg = 'INCAR contains KSPACING and KGAMMA: '
            if not kp:
                msg += 'KPOINTS omitted'
                self.use_kp = False
            else:
                msg += 'KPOINTS still used'
            self.logger.info(msg)

    def _prestore(self):
        super(TentativeVaspCalc, self)._prestore()
        self.elements = self.inp.structure.get_kind_names()

    def write_incar(self, inputdict, dst):
        from incar import dict_to_incar
        with open(dst, 'w') as incar:
            incar.write(dict_to_incar(inputdict['incar'].get_dict()))

    @classmethod
    def _get_paw_linkname(cls, kind):
        return 'paw_{}'.format(kind)

    def write_potcar(self, inputdict, dst):
        import subprocess32 as sp
        structure = inputdict['structure']
        catcom = ['cat']
        # order the symbols according to order given in structure
        for kind in structure.get_kind_names():
            paw = inputdict[self._get_paw_linkname(kind)]
            catcom.append(paw.get_abs_path('POTCAR'))
        # cat the pawdata nodes into the file
        with open(dst, 'w') as pc:
            sp.check_call(catcom, stdout=pc)

    def write_poscar(self, inputdict, dst):
        from ase.io.vasp import write_vasp
        structure = inputdict['structure']
        with open(dst, 'w') as poscar:
            write_vasp(poscar, structure.get_ase(), vasp5=True)

    def write_kpoints(self, inputdict, dst):
        if self.use_kp:
            kp = inputdict['kpoints']
            try:
                mesh, offset = kp.get_kpoints_mesh()
                with open(dst, 'w') as kpoints:
                    kps = kpmtemp.format(N=mesh, s=offset)
                    kpoints.write(kps)
            except AttributeError:
                kpl, weights = kp.get_kpoints(also_weights=True)
                kw = zip(kpl, weights)
                with open(dst, 'w') as kpoints:
                    kpls = '\n'.join([kplitemp.format(k[0], k[1]) for k in kw])
                    kps = kpltemp.format(N=len(kw), klist=kpls)
                    kpoints.write(kps)

    @property
    def elements(self):
        return self.get_attr('elements')

    @elements.setter
    def elements(self, value):
        self._set_attr('elements', value)

    @classmethod
    def make_new(cls, label, cifname, incar={}, kp={}, paw={}):
        from aiida.tools.codespecific.vasp.io import cif
        from aiida.tools.codespecific.vasp.default_paws import lda
        import os

        class Inputs(object):
            def __init__(self, label, incar, structure, potcars, kpoints):
                self.label = label
                self.incar = incar
                self.structure = structure
                self.potcars = potcars
                self.kpoints = kpoints
            def get_calc(self, cls=TentativeVaspCalc):
                calc = cls()
                calc.label = self.label
                calc.use_incar(self.incar)
                calc.use_structure(self.structure)
                for k, p in self.potcars.iteritems():
                    calc.use_paw(p, kind=k)
                calc.use_kpoints(self.kpoints)
                calc.set_computer
                return calc

        cifnode = cif.cif_from_file(cifname)
        namecifs = cif.get_cifs_with_name(os.path.basename(cifname))
        eqcifs = cif.filter_cifs_for_structure(namecifs, cifnode.get_ase())
        if eqcifs:
            cifnode = eqcifs[0]
        structure = cif.cif_to_structure(cifnode=cifnode)
        for kn in structure.get_kind_names():
            if not paw.get(kn):
                paw[kn] = cls.Paw().load_paw(family = 'LDA', symbol=lda[kn])[0]
        inc = cls._new_incar()
        inc.set_dict(incar)
        kpt = cls._new_kp()
        kpt.set_cell_from_structure(structure)
        if 'mesh' in kp:
            kpt.set_kpoints_mesh(kp['mesh'])
        elif 'list' in kp:
            kpt.set_kpoints(kp['list'])
        elif 'path' in kp:
            kpt.set_kpoints(kp['path'])
        return Inputs(label, inc, structure, paw, kpt)

    @classmethod
    def _new_incar(cls):
        return DataFactory('parameter')()

    @classmethod
    def _new_structure(cls):
        return DataFactory('structure')()

    @classmethod
    def Paw(cls):
        return DataFactory('vasp.potpaw')

    @classmethod
    def _new_kp(cls):
        return DataFactory('array.kpoints')()

class TestVC(VaspCalcBase):
    test_input = Input(types='parameter', doc='bla')
    default_parser = 'vasp.vasp'
