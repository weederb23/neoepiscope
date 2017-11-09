
class Transcript(object):
    """ Transforms transcript with edits (SNPs, indels) from haplotype """

    def __init__(self, bowtie_reference_index, CDS):
        """ Initializes Transcript object.

            This class assumes edits added to a transcript are properly
            phased, consistent, and nonredundant. Most conspicuously, there
            shouldn't be SNVs or insertions among deleted bases.

            bowtie_reference_index: BowtieIndexReference object for retrieving
                reference genome sequence
            CDS: list of all CDS lines for exactly one transcript from GTF;
                a line can be a list pre-split by '\t' or not yet split
        """
        assert len(CDS) > 0
        self.bowtie_reference_index = bowtie_reference_index
        self.intervals = []
        last_chrom, last_strand = None, None
        for line in CDS:
            if type(line) is str: line = line.strip().split('\t')
            try:
                assert last_chrom == line[0]
            except AssertionError:
                if last_chrom is None:
                    pass
                else:
                    raise
            try:
                assert last_strand == line[6]
            except AssertionError:
                if last_strand is None:
                    pass
                else: raise
            # Use exclusive start, inclusive end 0-based coordinates internally
            self.intervals.extend(
                    [int(line[3]) - 2, int(line[4]) - 1]
                )
            last_chrom, last_strand = line[0], line[6]
        # Store edits to coding sequence only
        self.edits = collections.defaultdict(list)
        self.deletion_intervals = []
        self.chrom = last_chrom
        self.rev_strand = (True if last_strand == '-' else False)
        '''Assume intervals are nonoverlapping! Uncomment following lines to
        check (slower).'''
        # for i in xrange(1, len(self.intervals)):
        #    if self.intervals[i-1] <= self.intervals[i]:
        #        raise RuntimeError(
        #                ('CDS intervals list '
        #                 '"{}" has overlapping intervals.').format(
        #                            self.intervals
        #                        )
        #            )
        # For retrieving save point
        self.last_edits = collections.defaultdict(list)
        self.last_deletion_intervals = []
        # Need to sort to bisect_left properly when editing!
        self.intervals.sort()

    def reset(self, reference=False):
        """ Resets to last save point or reference (i.e., removes all edits).

            reference: if False, tries to reset to last save point, and if that
                doesn't exist, resets to reference. If True, resets to 
                reference.

            No return value.
        """
        if reference:
            self.edits = collections.defaultdict(list)
            self.deletion_intervals = []
        else:
            self.edits = copy.copy(self.last_edits)
            self.deletion_intervals = copy.copy(self.last_deletion_intervals)

    def edit(self, seq, pos, mutation_type='V', mutation_class='S'):
        """ Adds an edit to the transcript. 

            seq: sequence to add or delete from reference; for deletions, all
                that matters is this sequence has the same length as the 
                sequence to delete. Also for deletions, seq can be an integer
                specifying how many bases to delete.
            pos: 1-based coordinate. For insertions, this is the coordinate 
                directly before the inserted sequence. For deletions, this 
                is the coordinate of the first base of the transcript to be
                deleted. Coordinates are always w.r.t. genome.
            mutation_type: V for SNV, I for insertion, D for deletion
            mutation_class: S for somatic, G for germline

            No return value.
        """
        if mutation_type == 'D':
            try:
                deletion_size = int(seq)
            except ValueError:
                deletion_size = len(seq)
            self.deletion_intervals.append(
                    (pos - 2, pos + deletion_size - 2, mutation_class)
                )
        elif mutation_type == 'V' or mutation_type == 'I':
            self.edits[pos - 1].append((seq, mutation_type, mutation_class))
        else:
            raise NotImplementedError('Mutation type not yet implemented')

    def expressed_edits(self, start=None, end=None, genome=True):
        """ Gets expressed set of edits and transcript intervals.

            start: start position (1-indexed, inclusive); None means start of
                transcript
            end: end position (1-indexed, inclusive); None means end of
                transcript
            genome: True iff genome coordinates are specified

            Return value: tuple (defaultdict
                                 mapping edits to lists of
                                 (seq, mutation_type, mutation_class)
                                 tuples, interval list; this is a list of 
                                 tuples (bound, {'R', 'G', or 'S'}), which
                                 says whether the bound is due to CDS bound
                                 ("R"), a germline deletion ("G"), or a 
                                 somatic deletion ("S"))
        """
        if not genome:
            raise NotImplementedError(
                'Retrieving sequence with transcript coordinates not '
                'yet fully supported.'
            )
        if start is None:
            start = self.intervals[0] + 1
        else:
            start -= 1
        if end is None:
            end = self.intervals[-1]
        else:
            end -= 1
        assert end >= start
        # Change start and end intervals of CDS intervals
        start_index = bisect.bisect_left(self.intervals, start)
        if not (start_index % 2):
            # start should be beginning of a CDS
            start_index += 1
            try:
                start = self.intervals[start_index - 1] + 1
            except IndexError:
                # Start is outside bounds of transcript
                return ''
        end_index = bisect.bisect_left(self.intervals, end)
        if not (end_index % 2):
            # end should be end of CDS
            end = self.intervals[end_index - 1]
            end_index -= 1
        intervals = [start - 1] + self.intervals[start_index:end_index] + [end]
        assert len(intervals) % 2 == 0
        # Include only relevant deletion intervals
        relevant_deletion_intervals, edits = [], collections.defaultdict(list)
        if self.deletion_intervals:
            sorted_deletion_intervals = sorted(self.deletion_intervals,
                                                key=itemgetter(0, 1))
            deletion_intervals = [(sorted_deletion_intervals[0][0],
                                   sorted_deletion_intervals[0][2]),
                                  (sorted_deletion_intervals[0][1],
                                   sorted_deletion_intervals[0][2])]
            for i in xrange(1, len(sorted_deletion_intervals)):
                if (sorted_deletion_intervals[i][0]
                    <= deletion_intervals[-1][0]):
                    deletion_intervals[-2] = min(deletion_intervals[-2],
                                            (sorted_deletion_intervals[i][0],
                                             sorted_deletion_intervals[i][2]),
                                            key=itemgetter(0))
                    deletion_intervals[-1] = max(deletion_intervals[-1],
                                            (sorted_deletion_intervals[i][1],
                                             sorted_deletion_intervals[i][2]),
                                            key=itemgetter(0))
                else:
                    deletion_intervals.extend(
                            [(sorted_deletion_intervals[i][0],
                                sorted_deletion_intervals[i][2]),
                             (sorted_deletion_intervals[i][1],
                                sorted_deletion_intervals[i][2])]
                        )
            for i in xrange(0, len(deletion_intervals), 2):
                start_index = bisect.bisect_left(intervals,
                                                    deletion_intervals[i][0])
                end_index = bisect.bisect_left(intervals,
                                                deletion_intervals[i+1][0])
                if start_index == end_index:
                    if start_index % 2:
                        # Entirely in a single interval
                        relevant_deletion_intervals.extend(
                                deletion_intervals[i:i+2]
                            )
                    # else deletion is entirely outside CDS within start/end
                else:
                    assert end_index > start_index
                    if start_index % 2:
                        pos = deletion_intervals[i]
                    else:
                        pos = (intervals[start_index], 'R')
                        start_index += 1
                    # deletion_intervals[i] becomes a new end
                    relevant_deletion_intervals.extend(
                            [pos, (intervals[start_index], 'R')]
                        )
                    if end_index % 2:
                        end_pos = deletion_intervals[i+1]
                        relevant_deletion_intervals.extend(
                            [(intervals[i], 'R') for i in
                             xrange(start_index + 1, end_index)]
                        )
                    else:
                        end_pos = (intervals[end_index - 1], 'R')
                        relevant_deletion_intervals.extend(
                                [(intervals[i], 'R') for i in
                                 xrange(start_index, end_index)]
                            )
                    relevant_deletion_intervals.append(end_pos)
        intervals = sorted([(interval, 'R') for interval in intervals]
                            + relevant_deletion_intervals)
        edits = collections.defaultdict(list)
        for pos in self.edits:
            # Add edit if and only if it's in one of the CDSes
            start_index = custom_bisect_left(intervals, pos)
            for edit in self.edits[pos]:
                if edit[1] == 'V':
                    if start_index % 2:
                        # Add edit if and only if it lies within CDS boundaries
                        edits[pos].append(edit)
                elif edit[1] == 'I':
                    if start_index % 2 or pos == intervals[start_index][0]:
                        '''An insertion is valid before or after a block'''
                        edits[pos].append(edit)
        return (edits, intervals)

    def save(self):
        """ Creates save point for edits.

            No return value.
        """
        self.last_edits = copy.copy(self.edits)
        self.last_deletion_intervals = copy.copy(self.deletion_intervals)

    def _seq_append(self, seq_list, seq, mutation_class):
        """ Appends mutation to seq_list, merging successive mutations.

            seq_list: list of tuples (sequence, type) where type is one
                of R, G, or S (for respectively reference, germline edit, or
                somatic edit). Empty sequence means there was a deletion.
            seq: seq to add
            mutation_class: S for somatic, G for germline, R for reference

            No return value; seq_list is merely updated.
        """
        try:
            condition = seq_list[-1][-1] == mutation_class
        except IndexError:
            # Add first item in seq_list
            assert not seq_list
            if seq or mutation_class != 'R':
                seq_list.append((seq, mutation_class))
            return
        if condition:
            seq_list[-1] = (seq_list[-1][0] + seq, mutation_class)
        elif seq or mutation_class != 'R':
            seq_list.append((seq, mutation_class))

    def annotated_seq(self, start=None, end=None, genome=True, 
        somatic=True, germline=True):
        """ Retrieves transcript sequence between start and end coordinates.

            Includes info on whether edits are somatic or germline and whether
            sequence is reference sequence.

            start: start position (1-indexed, inclusive); None means start of
                transcript
            end: end position (1-indexed, inclusive); None means end of
                transcript
            genome: True iff genome coordinates are specified
            somatic: True iff requesting return of tuples of type S
            germline: True iff requesting return of tuples of type G

            Return value: list of tuples (sequence, type) where type is one
                of R, G, or S (for respectively reference, germline edit, or
                somatic edit). Empty sequence means there was a deletion.
        """
        if end < start: return ''
        # Use 0-based coordinates internally
        if start is None:
            start = self.intervals[0] + 2
        if end is None:
            end = self.intervals[-1] + 1
        if genome:
            # Capture only sequence between start and end
            edits, intervals = self.expressed_edits(start, end, genome=True)
            '''Check for insertions at beginnings of intervals, and if they're
            present, shift them to ends of previous intervals so they're
            actually added.'''
            new_edits = copy.copy(edits)
            for i in xrange(0, len(intervals), 2):
                if intervals[i][0] in edits:
                    assert (len(edits[intervals[i][0]]) == 1
                                and edits[intervals[i][0]][0][1] == 'I')
                    if i:
                        new_edits[
                            intervals[i-1][0]] = new_edits[intervals[i][0]]
                        del new_edits[intervals[i][0]]
                    else:
                        intervals = [(-1, 'R'), (-1, 'R')] + intervals
                        # Have to add 2 because we modified intervals above
                        new_edits[-1] = new_edits[intervals[i+2][0]]
                        del new_edits[intervals[i+2][0]]
            seqs = []
            for i in xrange(0, len(intervals), 2):
                seqs.append(
                        self.bowtie_reference_index.get_stretch(
                                self.chrom, intervals[i][0] + 1,
                                intervals[i + 1][0] -
                                intervals[i][0]
                            )
                    )
            # Now build sequence in order of increasing edit position
            i = 1
            pos_group, final_seq = [], []
            for pos in (sorted(new_edits.keys()) + [(self.intervals[-1] + 1,
                                                        'R')]):
                if pos > intervals[i][0]:
                    last_index, last_pos = 0, intervals[i-1][0] + 1
                    for pos_to_add in pos_group:
                        fill = pos_to_add - last_pos
                        if intervals[i-1][1] != 'R':
                            self._seq_append(final_seq, '', intervals[i-1][1])
                        self._seq_append(final_seq, seqs[(i-1)/2][
                                            last_index:last_index + fill
                                        ], 'R')
                        if intervals[i][1] != 'R':
                            self._seq_append(final_seq, '', intervals[i][1])
                        # If no edits, snv is reference and no insertion
                        try:
                            snv = (seqs[(i-1)/2][last_index + fill], 'R')
                        except IndexError:
                            '''Should happen only for insertions at beginning
                            of sequence.'''
                            assert (i - 1) / 2 == 0 and not seqs[0]
                            snv = ('', 'R')
                        insertion = ('', 'R')
                        for edit in new_edits[pos_to_add]:
                            if edit[1] == 'V':
                                snv = (edit[0], edit[2])
                            else:
                                assert edit[1] == 'I'
                                insertion = (edit[0], edit[2])
                        self._seq_append(final_seq, *snv)
                        self._seq_append(final_seq, *insertion)
                        last_index += fill + 1
                        last_pos += fill + 1
                    if intervals[i-1][1] != 'R':
                        self._seq_append(final_seq, '', intervals[i-1][1])
                    self._seq_append(
                            final_seq, seqs[(i-1)/2][last_index:], 'R'
                        )
                    if intervals[i][1] != 'R':
                        self._seq_append(final_seq, '', intervals[i][1])
                    i += 2
                    try:
                        while pos > intervals[i]:
                            if intervals[i-1][1] != 'R':
                                self._seq_append(
                                        final_seq, '', intervals[i-1][1]
                                    )
                            self._seq_append(final_seq, seqs[(i-1)/2], 'R')
                            if intervals[i][1] != 'R':
                                self._seq_append(
                                        final_seq, '', intervals[i][1]
                                    )
                            i += 2
                    except IndexError:
                        if i > len(intervals) - 1:
                            # Done enumerating sequence
                            break
                    pos_group = [pos]
                else:
                    pos_group.append(pos)
            if self.rev_strand:
                return [(seq[::-1].translate(_revcomp_translation_table),
                            mutation_class)
                            for seq, mutation_class in final_seq][::-1]
            return final_seq
        raise NotImplementedError(
            'Retrieving sequence with transcript coordinates not '
            'yet fully supported.'
        )

    def peptides(self, size=9, somatic=True, germline=True):
        """ Retrieves list of predicted peptide fragments from transcript that 
            include one or more variants.

            size: peptide length (specified as # of amino acids)
            somatic: True iff requesting peptides containing variants of type S
            germline: True iff requesting peptides containing variants of type G

            Return value: list of peptides of desired length.
        """
        if size < 2: return []
        seq = self.annotated_seq(somatic=somatic, germline=germline)
        #extract list of transcript coordinates for each variant tuple
        #convert to string of nucleotides
        start = seq.find("ATG")
        if start < 0: return []
        protein = seq_to_peptide(seq[start:])
        # for each variant of type V, do the windows around there



