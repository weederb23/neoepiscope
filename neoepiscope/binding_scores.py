from __future__ import print_function
import os
import warnings
import tempfile
import pickle
import subprocess

neoepiscope_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_affinity_netMHCIIpan(peptides, allele, netmhciipan, version,
                                    scores, remove_files=True):
    """ Obtains binding affinities from list of peptides

        peptides: peptides of interest (list of strings)
        allele: Allele to use for binding affinity (string)
        netmhciipan: path to netMHCIIpan executable
        version: version of netMHCIIpan
        scores: list of scoring methods
        remove_files: option to remove intermediate files

        Return value: affinities (a list of binding affinities
                        as strings)
    """
    files_to_remove = []
    try:
        # Check that allele is valid for method
        with open(os.path.join(os.path.join(neoepiscope_dir, 'neoepiscope',
                                            'availableAlleles.pickle')
                        ), 'rb'
                ) as allele_stream:
            avail_alleles = pickle.load(allele_stream)
        # Homogenize format
        if 'DRB' in allele:
            allele = allele.replace('HLA-', '').replace(':', '').replace('*', '_')
        elif 'DP' in allele or 'DQ' in allele:
            allele.replace(':', '')
        if allele not in avail_alleles[''.join(['netMHCIIpan', str(version)])]:
            warnings.warn(' '.join([allele,
                                    'is not a valid allele for netMHCIIpan']),
                          Warning)
            if len(scores) == 1:
                return [(peptides[i], 'NA',) for i in range(0,len(peptides))]
            else:
                return [(peptides[i], 'NA', 'NA') for i in range(0,len(peptides))]
        allele = allele.replace('*', '_').replace(':', '')
        # Establish return list and sample id
        sample_id = '.'.join([peptides[0],
                                str(len(peptides)), allele,
                                'netmhciipan', version])
        affinities = []
        # Write one peptide per line to a temporary file for
        #   input if peptide length is at least 9
        # Count instances of smaller peptides
        na_count = 0
        peptide_file = tempfile.mkstemp(
                        suffix='.peptides', prefix='id.', text=True)[1]
        files_to_remove.append(peptide_file)
        with open(peptide_file, 'w') as f:
            for sequence in peptides:
                if len(sequence) >= 9:
                    print(sequence, file=f)
                else:
                    na_count += 1
        if na_count > 0:
            warnings.warn(' '.join([str(na_count),
                                    'peptides not compatible with',
                                    'netMHCIIpan will not receive score']),
                            Warning)
        # Establish temporary file to hold output
        mhc_out = tempfile.mkstemp(suffix='.netMHCIIpan.out',
                                    prefix='id.', text=True)[1]
        files_to_remove.append(mhc_out)
        # Run netMHCIIpan
        subprocess.check_call(
                        [netmhciipan, '-a', allele, '-inptype', '1',
                         '-xls', '-xlsfile', mhc_out, '-f', peptide_file]
                    )
        # Retrieve scores for valid peptides
        score_dict = {}
        with open(mhc_out, 'r') as f:
            # Skip headers
            f.readline()
            f.readline()
            for line in f:
                # token 1 is peptide; token 4 is affinity; token[5] is rank
                tokens = line.strip('\n').split('\t')
                if sorted(scores) == ['affinity', 'rank']:
                    score_dict[tokens[1]] = (tokens[4], tokens[5])
                elif sorted(scores) == ['affinity']:
                    score_dict[tokens[1]] = (tokens[4],)
                elif sorted(scores) == ['rank']:
                    score_dict[tokens[1]] = (tokens[5],)
        # Produce list of scores for valid peptides
        # Invalid peptides receive "NA" score
        for sequence in peptides:
            if sequence in score_dict:
                nM = (sequence,) + score_dict[sequence]
            else:
                if len(scores) == 1:
                    nM = (sequence, 'NA',)
                else:
                    nM = (sequence, 'NA', 'NA')
            affinities.append(nM)
        return affinities
    finally:
        if remove_files:
            for file_to_remove in files_to_remove:
                os.remove(file_to_remove)

def get_affinity_mhcflurry(peptides, allele, scores, version,
                                            remove_files=True):
    """ Obtains binding affinities from list of peptides

        peptides: peptides of interest (list of strings)
        allele: Allele to use for binding affinity (string)
        scores: list of scoring methods
        version: version of mhc-flurry
        remove_files: option to remove intermediate files

        Return value: affinities (a list of binding affinities
                        as strings)
    """
    files_to_remove = []
    try:
        # Check that allele is valid for method
        with open(os.path.join(neoepiscope_dir, 'neoepiscope',
                               'availableAlleles.pickle'), 'rb'
                ) as allele_stream:
            avail_alleles = pickle.load(allele_stream)
        if allele not in avail_alleles['mhcflurry']:
            warnings.warn(' '.join([allele,
                                    'is not a valid allele for mhcflurry']),
                          Warning)
            score_form = tuple(['NA' for i in range(0, len(scores))])
            return [(peptides[i],) + score_form for i in range(0,len(peptides))]
        # Establish return list and sample id
        sample_id = '.'.join([peptides[0],
                                str(len(peptides)), allele,
                                'mhcflurry', version])
        affinities = []
        # Write one peptide per line to a temporary file for
        #   input if peptide length is at least 9
        # Count instances of smaller peptides
        # Establish temporary file to hold output
        peptide_file = tempfile.mkstemp(suffix='.csv',
                                    prefix='id.', text=True)[1]
        na_count = 0
        with open(peptide_file, 'w') as f:
            f.write('allele,peptide\n')
            for sequence in peptides:
                if len(sequence) < 8 or len(sequence) > 15:
                    na_count += 1
                else:
                    print(''.join([allele, ',', sequence, '\n']), file=f)
        if na_count > 0:
            warnings.warn(' '.join([str(na_count),
                                    'peptides not compatible with',
                                    'mhcflurry will not receive score']),
                            Warning)
        # Establish temporary file to hold output
        mhc_out = tempfile.mkstemp(suffix='.mhcflurry.out',
                                    prefix='id.', text=True)[1]
        files_to_remove.append(mhc_out)
        # Run netMHCIIpan
        command = ['mhcflurry-predict', '--out', mhc_out, peptide_file]
        subprocess.check_call(command)
        # Retrieve scores for valid peptides
        score_dict = {}
        with open(mhc_out, 'r') as f:
            # Skip headers
            f.readline()
            for line in f:
                # token 1 is peptide; token 4 is affinity; token[5] is rank
                tokens = line.strip('\n').split(',')
                if sorted(scores) == ['affinity', 'rank']:
                    score_dict[tokens[1]] = (tokens[2], tokens[5])
                elif sorted(scores) == ['affinity', 'high', 'low', 'rank']:
                    score_dict[tokens[1]] = (tokens[2], tokens[4], tokens[3],
                                             tokens[5])
                elif sorted(scores) == ['affinity', 'high', 'low']:
                    score_dict[tokens[1]] = (tokens[2], tokens[4], tokens[3])
                elif sorted(scores) == ['affinity', 'high', 'rank']:
                    score_dict[tokens[1]] = (tokens[2], tokens[4], tokens[5])
                elif sorted(scores) == ['affinity', 'low', 'rank']:
                    score_dict[tokens[1]] = (tokens[2], tokens[3], tokens[5])
                elif sorted(scores) == ['high', 'low', 'rank']:
                    score_dict[tokens[1]] = (tokens[4], tokens[3], tokens[3])
                elif sorted(scores) == ['affinity', 'high']:
                    score_dict[tokens[1]] = (tokens[2], tokens[4])
                elif sorted(scores) == ['affinity', 'low']:
                    score_dict[tokens[1]] = (tokens[2], tokens[3])
                elif sorted(scores) == ['high', 'low']:
                    score_dict[tokens[1]] = (tokens[4], tokens[3])
                elif sorted(scores) == ['high', 'rank']:
                    score_dict[tokens[1]] = (tokens[4], tokens[5])
                elif sorted(scores) == ['low', 'rank']:
                    score_dict[tokens[1]] = (tokens[3], tokens[5])
                elif sorted(scores) == ['affinity']:
                    score_dict[tokens[1]] = (tokens[2],)
                elif sorted(scores) == ['rank']:
                    score_dict[tokens[1]] = (tokens[5],)
                elif sorted(scores) == ['high']:
                    score_dict[tokens[1]] = (tokens[4],)
                elif sorted(scores) == ['low']:
                    score_dict[tokens[1]] = (tokens[3],)
        # Produce list of scores for valid peptides
        # Invalid peptides receive "NA" score
        for sequence in peptides:
            if sequence in score_dict:
                nM = (sequence,) + score_dict[sequence]
            else:
                nM = (sequence,) + tuple(['NA' for i in range(0, len(scores))])
            affinities.append(nM)
        return affinities
    finally:
        if remove_files:
            for file_to_remove in files_to_remove:
                os.remove(file_to_remove)

def get_affinity_netMHCpan(peptides, allele, netmhcpan, version, scores,
                                remove_files=True):
    """ Obtains binding affinities from list of peptides

        peptides: peptides of interest (list of strings)
        allele: allele to use for binding affinity
                    (string, format HLA-A02:01)
        netmhcpan: path to netMHCpan executable
        version: version of netMHCpan software
        scores: list of scoring methods
        remove_files: option to remove intermediate files

        Return value: affinities (a list of binding affinities
                        as strings)
    """
    files_to_remove = []
    try:
        # Check that allele is valid for method
        with open(os.path.join(neoepiscope_dir, 'neoepiscope',
                                'availableAlleles.pickle'), 'rb'
                ) as allele_stream:
            avail_alleles = pickle.load(allele_stream)
        allele = allele.replace('*', '')
        if allele not in avail_alleles[''.join(['netMHCpan', str(version)])]:
            warnings.warn(' '.join([allele,
                                    'is not a valid allele for netMHCpan']),
                            Warning)
            if len(scores) == 1:
                return [(peptides[i], 'NA',) for i in range(0,len(peptides))]
            else:
                return [(peptides[i], 'NA', 'NA') for i in range(0,len(peptides))]
        # Establish return list and sample id
        sample_id = '.'.join([peptides[0], str(len(peptides)),
                                allele, 'netmhcpan', version])
        affinities = []
        # Write one peptide per line to a temporary file for input
        peptide_file = tempfile.mkstemp(suffix='.peptides',
                                        prefix=''.join([sample_id,
                                                        '.']),
                                        text=True)[1]
        files_to_remove.append(peptide_file)
        with open(peptide_file, 'w') as f:
            for sequence in peptides:
                print(sequence, file=f)
        # Establish temporary file to hold output
        mhc_out = tempfile.mkstemp(suffix='.netMHCpan.out',
                                    prefix=''.join([sample_id,
                                                    '.']),
                                    text=True)[1]
        files_to_remove.append(mhc_out)
        # Run netMHCpan
        if version == '3':
            subprocess.check_call(
                [netmhcpan, '-a', allele, '-inptype', '1', '-p', '-xls',
                    '-xlsfile', mhc_out, peptide_file])
        elif version == '4':
            subprocess.check_call(
                [netmhcpan, '-BA', '1', '-a', allele, '-inptype', '1', '-p', '-xls',
                    '-xlsfile', mhc_out, peptide_file])
        with open(mhc_out, 'r') as f:
            f.readline()
            f.readline()
            for i in range(0, len(peptides)):
                tokens = f.readline().strip('\n').split('\t')
                # for v3, tokens[5] is affinity, tokens[6] is rank
                # for v4, tokens[6] is affinty, tokens[7] is rank
                if sorted(scores) == ['affinity', 'rank']:
                    if version == '3':
                        nM = (peptides[i], tokens[5], tokens[6])
                    elif version == '4':
                        nM = (peptides[i], tokens[6], tokens[7])
                elif sorted(scores) == ['affinity']:
                    if version == '3':
                        nM = (peptides[i], tokens[5], )
                    elif version == '4':
                        nM = (peptides[i], tokens[6], )
                elif sorted(scores) == ['rank']:
                    if version == '3':
                        nM = (peptides[i], tokens[6], )
                    elif version == '4':
                        nM = (peptides[i], tokens[7], )
                affinities.append(nM)
        return affinities
    finally:
        # Remove temporary files
        if remove_files:
            for file_to_remove in files_to_remove:
                os.remove(file_to_remove)

def gather_binding_scores(neoepitopes, tool_dict, hla_alleles):
    """ Adds binding scores from desired programs to neoepitope metadata

        neoepitopes: dictionary linking neoepitopes to their metadata
        tool_dict: dictionary storing prediction tool data
        hla_alleles: list of HLA alleles used for binding predictions

        Return value: dictionary linking neoepitopes to their metadata,
            which now includes binding scores
    """
    for allele in hla_alleles:
        for tool in sorted(tool_dict.keys()):
            if tool == 'mhcflurry1':
                binding_scores = get_affinity_mhcflurry(
                                                neoepitopes.keys(),
                                                allele, tool_dict[tool][1],
                                                '1',
                                                remove_files=True
                                                )
            if tool == 'netMHCIIpan3':
                binding_scores = get_affinity_netMHCIIpan(
                                                neoepitopes.keys(),
                                                allele, tool_dict[tool][0],
                                                '3',
                                                tool_dict[tool][1],
                                                remove_files=True
                                                )
            elif tool == 'netMHCpan3':
                binding_scores = get_affinity_netMHCpan(
                                                neoepitopes.keys(),
                                                allele, tool_dict[tool][0],
                                                '3', tool_dict[tool][1],
                                                remove_files=True
                                                )
            elif tool == 'netMHCpan4':
                binding_scores = get_affinity_netMHCpan(
                                                neoepitopes.keys(),
                                                allele, tool_dict[tool][0],
                                                '4', tool_dict[tool][1],
                                                remove_files=True
                                                )
            for score in binding_scores:
                meta_data = neoepitopes[score[0]]
                for i in range(0, len(meta_data)):
                    neoepitopes[score[0]][i] = (
                                meta_data[i] + score[1:]
                            )
    return neoepitopes
