from __future__ import print_function
import subprocess
import warnings
import collections

def adjust_tumor_column(in_vcf, out_vcf):
    """ Swaps the sample columns in a somatic vcf

        HAPCUT2 only takes data from the first VCF sample column, so if the 
            tumor sample data is in the second VCF sample column, it must be
            swapped prior to optional germline merging or running HAPCUT2

        in_vcf: input vcf that needs the tumor sample data flipped
        out_vcf: output vcf to have the correct columns

        No return value.
    """
    header_lines = []
    other_lines = []
    # Process input vcf
    with open(in_vcf, 'r') as f:
        for line in f:
            # Preserve header lines with out change
            if line[0:2] == '##':
                header_lines.append(line.strip('\n'))
            # Adjust column header and variant lines
            else:
                tokens = line.strip('\n').split('\t')
                if line[0] == '#':
                    warnings.warn(''.join(['Reading ', tokens[9], 
                                           'as normal tissue and ', tokens[10],
                                           'as tumor tissue']), 
                                  Warning)
                new_line = '\t'.join([tokens[0], tokens[1], tokens[2], 
                                        tokens[3], tokens[4], tokens[5], 
                                        tokens[6], tokens[7], tokens[8], 
                                        tokens[10], tokens[9]])
                other_lines.append(new_line)
    # Write new vcf
    with open(out_vcf, 'w') as f:
        for line in header_lines:
            f.write(line + '\n')
        for line in other_lines:
            f.write(line + '\n')

def combine_vcf(vcf1, vcf2, outfile='Combined.vcf'):
    """ Combines VCFs

        No return value.
    """
    vcffile = open(vcf2, 'r')
    temp = open(vcf2 + '.tumortemp', 'w+');
    header = open(vcf2 + '.header', 'w+');
    for lines in vcffile:
        if (lines[0] != '#'):
            temp.write(lines)
        else:
            header.write(lines)
    vcffile.close()
    temp.close()
    header.close()
    vcffile = open(vcf1, 'r')
    temp = open(vcf2 + '.germlinetemp', 'w+');
    for lines in vcffile:
        if (lines[0] != '#'):
            temp.write(lines)
    vcffile.close()
    temp.close()    
    markgermline = ''.join(['''awk '{print $0"*"}' ''', vcf2, 
                            ".germlinetemp > ", vcf2, '.germline'])
    marktumor    = ''.join(['''awk '{print $0}' ''', vcf2, 
                            '.tumortemp > ', vcf2, '.tumor'])
    subprocess.call(markgermline, shell=True)
    subprocess.call(marktumor, shell=True)
    command = ''.join(['cat ', vcf2, '.germline ', vcf2, '.tumor > ', 
                        vcf2, '.combine1'])
    subprocess.call(command, shell=True)
    command2 = ''.join(['sort -k1,1 -k2,2n ', vcf2, '.combine1 > ', 
                        vcf2, '.sorted'])
    subprocess.call(command2, shell=True)
    command3 = ''.join(['cat ', vcf2, '.header ', vcf2, '.sorted > ', 
                        vcf2, '.combine2'])
    subprocess.call(command3, shell=True)
    cut = ''.join(['cut -f1,2,3,4,5,6,7,8,9,10 ', vcf2, 
                    '.combine2 > ', outfile])
    subprocess.call(cut, shell=True)
    for file in ['.tumortemp', '.germlinetemp', '.combine1', '.combine2', 
                    '.sorted', '.tumor', '.germline', '.header']:
        cleanup = ''.join(['rm ', vcf2, file])
        subprocess.call(cleanup, shell=True)

def prep_hapcut_output(output, hapcut2_output, vcf):
    """ Adds unphased mutations to HapCUT2 output as their own haplotypes
        
        output: path to output file to write adjusted haplotypes
        hapcut2_output: path to original output from HapCUT2 with only 
            phased mutations
        vcf: path to vcf used to generate original HapCUT2 output

        Return value: None
    """
    phased = collections.defaultdict(set)
    with open(output, 'w') as output_stream:
        with open(hapcut2_output) as hapcut2_stream:
            for line in hapcut2_stream:
                if line[0] != '*' and not line.startswith('BLOCK'):
                    tokens = line.strip().split('\t')
                    phased[(tokens[3], int(tokens[4]))].add(
                                                    (tokens[5], tokens[6])
                                                )
                print(line.strip(), file=output_stream)
        print('********', file=output_stream)
        with open(vcf) as vcf_stream:
            first_char = '#'
            while first_char == '#':
                line = vcf_stream.readline().strip()
                try:
                    first_char = line[0]
                except IndexError:
                    first_char = '#'
            counter = 1
            while line:
                tokens = line.split('\t')
                pos = int(tokens[1])
                alt_alleles = tokens[4].split(',')
                for allele in alt_alleles:
                    if (tokens[3], allele) not in phased[
                                                (tokens[0], pos)
                                            ]:
                        print('BLOCK: unphased', file=output_stream)
                        print(('{vcf_line}\t1\t0\t{chrom}\t'
                               '{pos}\t{ref}\t{alt}\t'
                               '{genotype}\tNA\tNA').format(
                                    vcf_line=counter,
                                    chrom=tokens[0],
                                    pos=pos,
                                    ref=tokens[3],
                                    alt=tokens[4],
                                    genotype=tokens[9]
                                ), file=output_stream)
                        print('********', file=output_stream)
                line = vcf_stream.readline().strip()
                counter += 1

def which(path):
    """ Searches for whether executable is present and returns version

        path: path to executable

        Return value: None if executable not found, else string with software
            name and version number
    """
    try:
        subprocess.check_call([path])
    except OSError as e:
        return None
    else:
        return path

def get_VAF_pos(VCF):
    """ Obtains position in VCF format/genotype fields of VAF

        VCF: path to input VCF

        Return value: None if VCF does not contain VAF, 
                        otherwise position of VAF
    """
    VAF_check = False
    with open(VCF) as f:
        for line in f:
            # Check header lines to see if FREQ exits in FORMAT fields
            if line[0] == '#':
                if 'FREQ' in line:
                    VAF_check = True
            else:
                # Check first entry to get position of FREQ if it exists
                if VAF_check:
                    tokens = line.strip('\n').split('\t')
                    format_field = tokens[8].split(':')
                    for i in range(0,len(format_field)):
                        if format_field[i] == 'FREQ':
                            VAF_pos = i
                            break
                # Return None if VCF does not contain VAF data
                else:
                    VAF_pos = None
                    break
    return VAF_pos

def write_results(output_file, hla_alleles, neoepitopes, tool_dict):
    """ Writes predicted neoepitopes out to file
        
        output_file: path to output file
        hla_alleles: list of HLA alleles used for binding predictions
        neoepitopes: dictionary linking neoepitopes to their metadata
        tool_dict: dictionary storing prediction tool data

        Return value: None.   
    """
    with open(output_file, 'w') as o:
        headers = ['Neoepitope', 'Chromsome', 'Pos', 'Ref', 'Alt', 
                   'Mutation_type', 'VAF', 'Warnings', 'Transcript_ID']
        for allele in hla_alleles:
            for tool in sorted(tool_dict.keys()):
                for score_method in sorted(tool_dict[tool][1]):
                    headers.append('_'.join([tool, allele, score_method]))
        o.write('\t'.join(headers) + '\n')
        for epitope in sorted(neoepitopes.keys()):
            if len(neoepitopes[epitope]) == 1:
                mutation = neoepitopes[epitope][0]
                if mutation[2] == '':
                    ref = '*'
                else:
                    ref = mutation[2]
                if mutation[3] == '':
                    alt = '*'
                else:
                    alt = mutation[3]
                if mutation[5] is None:
                    VAF = 'NA'
                else:
                    VAF = str(mutation[5])
                out_line = [epitope, mutation[0], str(mutation[1]), ref, alt,
                            mutation[4], VAF, mutation[6],
                            mutation[7]]
                for i in range(7,len(mutation)):
                    out_line.append(str(mutation[i]))
                o.write('\t'.join(out_line) + '\n')
            else:
                mutation_dict = collections.defaultdict(list)
                ep_scores = []
                for i in range(8, len(neoepitopes[epitope][0])):
                    ep_scores.append(neoepitopes[epitope][0][i])
                for mut in neoepitopes[epitope]:
                    if mut[2] == '':
                        ref = '*'
                    else:
                        ref = mut[2]
                    if mut[3] == '':
                        alt = '*'
                    else:
                        alt = mut[3]
                    if mut[5] is None:
                        VAF = 'NA'
                    else:
                        VAF = str(mut[5])
                    mutation_dict[(mut[0], mut[1], ref, alt, mut[4])].append(
                                                                [VAF, mut[6],
                                                                 mut[7]]
                                                                 )
                for mut in sorted(mutation_dict.keys()):
                    out_line = [epitope, mut[0], str(mut[1]), mut[2], mut[3],
                                mut[4],
                                ';'.join(
                                        [str(x[0]) for x in mutation_dict[mut]]
                                        ),
                                ';'.join(
                                        [str(x[1]) for x in mutation_dict[mut]]
                                        ),
                                ';'.join(
                                        [str(x[2]) for x in mutation_dict[mut]]
                                        )]
                    for score in ep_scores:
                        out_line.append(str(score))
                    o.write('\t'.join(out_line) + '\n')