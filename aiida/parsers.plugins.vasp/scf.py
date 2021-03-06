from basic import BasicParser


class ScfParser(BasicParser):
    def parse_with_retrieved(self, retrieved):
        super(ScfParser, self).parse_with_retrieved(retrieved)

        self.set_kpoints(self.read_ibzkpt())
        self.set_chgcar(self.get_chgcar())
        self.set_wavecar(self.get_wavecar())
        return self.result(success=True)
