import bisect
import argparse
import bowtie_index
import sys
import math
import string
import copy
import pickle

codon_table = {"TTT":"F", "TTC":"F", "TTA":"L", "TTG":"L",
    "TCT":"S", "TCC":"S", "TCA":"S", "TCG":"S",
    "TAT":"Y", "TAC":"Y", "TAA":"Stop", "TAG":"Stop",
    "TGT":"C", "TGC":"C", "TGA":"Stop", "TGG":"W",
    "CTT":"L", "CTC":"L", "CTA":"L", "CTG":"L",
    "CCT":"P", "CCC":"P", "CCA":"P", "CCG":"P",
    "CAT":"H", "CAC":"H", "CAA":"Q", "CAG":"Q",
    "CGT":"R", "CGC":"R", "CGA":"R", "CGG":"R",
    "ATT":"I", "ATC":"I", "ATA":"I", "ATG":"M",
    "ACT":"T", "ACC":"T", "ACA":"T", "ACG":"T",
    "AAT":"N", "AAC":"N", "AAA":"K", "AAG":"K",
    "AGT":"S", "AGC":"S", "AGA":"R", "AGG":"R",
    "GTT":"V", "GTC":"V", "GTA":"V", "GTG":"V",
    "GCT":"A", "GCC":"A", "GCA":"A", "GCG":"A",
    "GAT":"D", "GAC":"D", "GAA":"E", "GAG":"E",
    "GGT":"G", "GGC":"G", "GGA":"G", "GGG":"G"}

def turn_to_aa(nucleotide_string, strand="+"):
    aa_string = ""
    num_aa = 0
    if strand == "-":
        translation_table = string.maketrans("ATCG", "TAGC")
        nucleotide_string = nucleotide_string.translate(translation_table)[::-1]
    for aa in range(len(nucleotide_string)//3):
        num_aa += 1
        try:
            codon = codon_table[nucleotide_string[3*aa:3*aa+3]]
        except KeyError:
            print >>sys.stderr, (
                        'Could not translate nucleotide string "{}".'
                    ).format(nucleotide_string)
            return False
        if codon == "Stop":
            aa_string += (len(nucleotide_string)//3 - num_aa)*'X'
            break
        else:
            aa_string += codon
    return aa_string

def my_print_function(kmer_list, mute_posits):
    if len(kmer_list)==0: return None
    for wtmtPair in kmer_list:
        wt,mt = wtmtPair
        print(wt + "\t" + mt + "\t" + str(mute_posits))
    return None


def kmer(mute_posits, normal_aa, mutated_aa = ""):
    if (len(mutated_aa) == 0):
        mutated_aa = normal_aa
    kmer_list = list()
    #Loop through window sizes
    for ksize in range(8, 12):
        for startIndex in range(len(mutated_aa)-ksize):
            kmer_list.append((normal_aa[startIndex:startIndex+ksize], mutated_aa[startIndex:startIndex+ksize]))
    final_list = list()
    for WT,MT in kmer_list:
        if (WT != MT):
            final_list.append((WT, MT))
    my_print_function(final_list, mute_posits)
    return final_list

def get_cds(transcript_id, mutation_pos_list, seq_length_left, 
              seq_length_right, cds_dict, mute_dict):
    ''' References cds_dict to get cds Bounds for later Bowtie query.

        transcript_id: (String) Indicates the transcript the mutation
            is located on.
        mutation_pos_list: (int) Mutation's position on chromosome
        seq_length_left: (int) How many bases must be gathered
            to the left of the mutation
        seq_length_right: (int) How many bases must be gathered to
            the right of the mutation

        Return value: List of tuples containing starting indexes and stretch
        lengths within cds boundaries necessary to acquire the complete 
        sequence necessary for 8-11' peptide kmerization based on the position 
        of a mutation within a chromosome.
    '''
    ordered_cds_dict = cds_dict
    if transcript_id not in ordered_cds_dict:
        return [], mute_locs
    pos_in_codon = 2 - (seq_length_right%3)
    cds_list = ordered_cds_dict[transcript_id]
    mutation_pos = -1
    #Don't want to check rightmost since seq. queries based off of it.
    if len(mutation_pos_list) >= 2:
        removal_list = []
        shift = mutation_pos_list[0][0] - min(mute_dict)
        #Remove all mutations outside of cds boundaries.
        for index in range(len(mutation_pos_list)):
            lower_cds_index = 2*bisect.bisect(cds_list[::2], mutation_pos_list[index][0])-2
            upper_cds_index = lower_cds_index+1
            if(lower_cds_index < 0 or 
               cds_list[upper_cds_index] < mutation_pos_list[index][0]):
                #Delete at the current index
                try:
                    del mute_dict[mutation_pos_list[index][0] - shift]
                    removal_list.append(index)
                except KeyError:
                    continue
        for index in range(len(removal_list)-1, -1, -1):
            print("made edits to mute pos list")
            mutation_pos_list.pop(removal_list[index])
    #Loop again, this time from right & correcting seq queries.
    for index in range(len(mutation_pos_list)-1, -1, -1):
        mutation = mutation_pos_list[index][0]
        middle_cds_index = 2*bisect.bisect(cds_list[::2], mutation)-2
        #If the middle_cds_index is past the last boundary, move it to the last
        if middle_cds_index > len(cds_list)-1:
            middle_cds_index -= 2
        #If the biggest position is smaller than the smallest bound, return []
        if middle_cds_index < 0:
            return [], mute_locs
        curr_left_index = middle_cds_index
        curr_right_index = middle_cds_index+1 #cds boundary end indexes
        #Increase by one to ensure mutation_pos_list is collected into boundary
        curr_pos_left = mutation + 1
        curr_pos_right = mutation #Actual number in chromosome
        #If the mutation is not on in cds bounds, return [].
        if(mutation <= cds_list[curr_right_index] and 
           mutation >= cds_list[curr_left_index]):
            mutation_pos = mutation
            if index != len(mutation_pos_list)-1:
                #shift is the current mutation's position in the codon.
                new_pos_in_codon = (mutation_pos_list[-1][0]
                                    - pos_in_codon-mutation_pos_list[index][0]) % 3
                seq_length_right = 30 + new_pos_in_codon
                seq_length_left -= (mutation_pos_list[-1][0] 
                                    - mutation_pos_list[index][0])
            break
    if(mutation_pos == -1):
        return [], mute_locs
    #Increase the seq length by 1 to account for mutation_pos_list collection
    seq_length_left += 1
    total_seq_length = seq_length_right + seq_length_left
    original_length_left = seq_length_left
    nucleotide_index_list = []
    #Loop left until receive all queried left-side bases and mutation base.
    while(len(nucleotide_index_list) == 0 or 
          sum([index[1] for index in nucleotide_index_list]) 
          < (original_length_left)):
        if curr_pos_left-cds_list[curr_left_index] >= seq_length_left:
            if curr_pos_left != mutation_pos+1:
                nucleotide_index_list.append((curr_pos_left-seq_length_left+1,
                                          seq_length_left))
            else:
                nucleotide_index_list.append((curr_pos_left-seq_length_left,
                                          seq_length_left))
            seq_length_left = 0
        else:
            nucleotide_index_list.append((cds_list[curr_left_index],
                                    curr_pos_left-cds_list[curr_left_index]))
            seq_length_left -= curr_pos_left-cds_list[curr_left_index]
            curr_pos_left = cds_list[curr_left_index-1]
            curr_left_index -= 2
            if curr_left_index < 0:
                #print("Exceeded all possible cds boundaries!")
                #Changed total_seq_length for comparison in next while loop.
                total_seq_length = (original_length_left
                                      - seq_length_left
                                      + seq_length_right)
                break
    #Reverse list to get tuples in order
    nucleotide_index_list = list(reversed(nucleotide_index_list))
    while(len(nucleotide_index_list) == 0 or 
              sum([index[1] for index in nucleotide_index_list]) 
              < (total_seq_length)):
        if cds_list[curr_right_index] >= curr_pos_right + seq_length_right:
            if curr_pos_right == mutation_pos:
                nucleotide_index_list.append((curr_pos_right+1,
                                              seq_length_right))
            else:
                nucleotide_index_list.append((curr_pos_right,
                                              seq_length_right))
            seq_length_right = 0
        else:
            try:
                nucleotide_index_list.append((curr_pos_right+1,
                                              cds_list[curr_right_index]
                                              - curr_pos_right))
                seq_length_right -= cds_list[curr_right_index]-curr_pos_right
                curr_pos_right = cds_list[curr_right_index+1]
                curr_right_index += 2
            except IndexError:
                #print("Exceeded all possible cds boundaries!")
                break
    return nucleotide_index_list, mute_dict

def find_stop(query_st, trans_id, line_count, exon_dict, chrom, ref_ind, mute_locs, reverse):
    until_stop = ""
    start = query_st
    stop_found = False
    (l_query, r_query) = (0, 33)
    if reverse:
        (l_query, r_query) = (r_query, l_query)
    while(stop_found == False):
        (exon_list, temp_out) = get_cds(trans_id, [(start,line_count)], l_query, r_query, exon_dict, mute_locs)
        extra_cods = ""
        for bound_start, bound_stretch in exon_list:
            extra_cods += get_seq(chrom, bound_start, bound_stretch, ref_ind)
        if reverse:
            start = exon_list[0][0]
        else:
            start = exon_list[-1][0] + exon_list[-1][1]
        count = 0
        while(count<33):
            if reverse:
                new_codon = extra_cods[30-count:33-count]
                count += 3
                amino_acid = turn_to_aa(new_codon, "-")
            else:
                new_codon = extra_cods[count: count+3]
                count += 3
                amino_acid = turn_to_aa(new_codon)
            if(amino_acid==""):
                stop_found = True
                break
            if reverse:
                until_stop = new_codon + until_stop
            else:
                until_stop += new_codon
    return until_stop

def get_seq(chrom, start, splice_length, ref_ind):
    chr_name = "chr" + chrom #proper
    start -= 1 #adjust for 0-based bowtie queries
    try:
        seq = ref_ind.get_stretch(chr_name, start, splice_length)
    except KeyError:
        return False
    return seq

def make_mute_seq(orig_seq, mute_locs):
    mute_seq = ""
    for ind in range(len(orig_seq)):
        if ind in mute_locs:
            mute_seq += mute_locs[ind]
        else:
            mute_seq += orig_seq[ind]
    return mute_seq

def find_seq_and_kmer(cds_list, last_chrom, ref_ind, mute_locs,
                      orf_dict, trans_id, mute_posits):
    wild_seq = ""
    full_length = 0
    for cds_stretch in cds_list:
        (seq_start, seq_length) = cds_stretch
        try:
            wild_seq += get_seq(last_chrom, seq_start, seq_length, ref_ind)
        except:
            return
        full_length += seq_length
    cds_start = cds_list[0][0]
    #for mute in mute_locs:
    #   personal_wild_seq_set = austin_script(cds_list, wild_seq)
    mute_seq = make_mute_seq(wild_seq,mute_locs)
    kmer(mute_posits,
        turn_to_aa(wild_seq, orf_dict[trans_id][0][0]), 
        turn_to_aa(mute_seq, orf_dict[trans_id][0][0])
        )


parser = argparse.ArgumentParser()
parser.add_argument('-v', '--vcf', type=str, required=False,
        default='-',
        help='input vcf or "-" for stdin'
    )
parser.add_argument('-x', '--bowtie-index', type=str, required=True,
        help='path to Bowtie index basename'
    )
parser.add_argument('-d', '--dicts', type=str, required=True,
        help='input path to pickled dictionaries'
    )
args = parser.parse_args()
ref_ind = bowtie_index.BowtieIndexReference(args.bowtie_index)

my_dicts = pickle.load ( open (args.dicts, "rb"))
(cds_dict, orf_dict, exon_dict, exon_orf_dict) = (my_dicts[0], my_dicts[1], my_dicts[2], my_dicts[3])


try:
    if args.vcf == '-':
        if sys.stdin.isatty():
            raise RuntimeError('Nothing piped into this script, but input is '
                               'to be read from stdin')
        else:
            input_stream = sys.stdin
    else:
        input_stream = open(args.vcf, "r")
        last_chrom = "None"
        line_count = 0
        orig_seq = ""
        mute_locs = {}
        mute_posits = []
        my_dict = cds_dict
        for line in input_stream:
            line_count += 1
            if not line or line[0] == '#': continue
            vals = line.strip().split('\t')
            (chrom, pos, orig, alt, info) = (vals[0], int(vals[1]), vals[3], vals[4], vals[7]
                )
            tokens = info.strip().split('|')
            mute_type = tokens[1]
            if(mute_type != "missense_variant" and len(orig) == len(alt)): 
                continue
            (trans_id) = (tokens[6])
            if mute_type == "missense_variant":
                rel_pos = int(tokens[13])
                pos_in_codon = (rel_pos+2)%3 #ie: ATG --> 0,1,2
            try:
                if orf_dict[trans_id][0][0] == "-" and mute_type == "missense_variant": 
                    pos_in_codon = 2-pos_in_codon
            except:
                continue
            '''
            if mute_type == "missense_variant":
                #Basic code for checking for mutation membership within cds/exon regions
                #Note: THIS DOES NOT FIX THE ISSUE! It pulls 33 from both sides
                # while it should only be pulling from one side!
                # Also, we need to think of what happens if the 33 go past the start codon.
                # It would read as a "M" in our peptide seqn atm (which is wrong)
                # Also, changing to the exon_dict() produces the wrong reading frame since
                # we are starting calculations from the wrong point
                try:
                    cds_list = cds_dict[trans_id]
                except KeyError:
                    print("It seems like that transcript does not exist in the cds_dict!")
                lower_cds_index = 2*bisect.bisect(cds_list[::2], pos)-2
                upper_cds_index = lower_cds_index+1
                if(lower_cds_index >= 0 and cds_list[lower_cds_index] <= pos
                    and cds_list[upper_cds_index] >= pos
                  ):
                    my_dict = exon_dict
                else:
                    exon_list = exon_dict[trans_id]
                    lower_exon_index = 2*bisect.bisect(exon_list[::2], pos)-2
                    upper_exon_index = lower_exon_index+1
                    if(lower_exon_index >= 0 and exon_list[lower_exon_index] <= pos and
                        exon_list[upper_exon_index] >= pos
                      ):
                        start = (pos-pos_in_codon if strand=="+" else pos+pos_in_codon)
                        wild_codon = get_seq(chrom, start, 3, ref_ind)
                        #If it's a start codon, then good luck!
                        mutated_codon = turn_to_aa(wild_codon[:pos_in_codon] + alt
                                        + wild_codon[pos_in_codon+1:])
                        if mutated_codon == "M":
                            my_dict = exon_dict
                        else:
                            print("Mutation does not lie within coding boundaries!")
                            continue
            '''
            if((last_chrom != "None") and ((pos-last_pos > (32-pos_in_codon)) or last_chrom != chrom)):
                (left_side,right_side) = (last_pos-st_ind,end_ind-last_pos)
                (cds_list, mute_locs) = get_cds(trans_id, mute_posits, left_side, right_side, my_dict, mute_locs)
                if(len(cds_list) != 0):
                    find_seq_and_kmer(cds_list, last_chrom, ref_ind,
                                      mute_locs, orf_dict, trans_id, mute_posits)
                (mute_locs, mute_posits) = (dict(), [])
            if len(orig) != len(alt):
                try:
                    cds_list = cds_dict[trans_id]
                except:
                    continue
                orf_list = orf_dict[trans_id]
                cds_index = 2*bisect.bisect(cds_list[::2], pos)-2
                (cds_start, cds_end) = (cds_list[cds_index], cds_list[cds_index+1]) 
                orf = orf_list[cds_index//2]
                (strand, frame) = (orf[0], orf[1])
                #if(strand == "-"):
                #    continue ## DELETE later
                pos_in_codon = (pos - cds_start - int(frame))%3 #check math
                if(strand != "+"):
                    #Check math.
                    pos_in_codon = (3 - (((cds_end-(pos+1)) - int(frame))%3))%3
                    #pos_in_codon = 2-pos_in_codon
            ## SOLVE for case in which indel is very first mutation
            '''try:
                if((pos-last_pos <= (32-pos_in_codon)) and (len(orig) != len(alt))
                    and (orf[0] != "+")):
                        (mute_locs, mute_posits) = (dict(), [])
            except:
                continue
            if((last_chrom != "None") and (pos-last_pos <= (32-pos_in_codon)) and (len(orig) != len(alt))
                 and (orf[0] != "+")):
                    (mute_locs, mute_posits) = (dict(), [])'''
            if len(orig) != len(alt):
                shift = len(alt)-len(orig)
                mute_posits.append((pos, line_count))
                if strand == "-":
                    #end_ind = pos + 32 - (pos_in_codon+shift)%3
                    st_ind = query_st = pos-pos_in_codon
                    if len(alt) > len(orig):
                        #print "Insertion"
                        end_ind = pos + 32 - (pos_in_codon+shift)%3
                        mute_locs[pos-st_ind] = alt
                    else:
                        #print "Deletion"
                        end_ind = pos + 32 - pos_in_codon + abs(shift)
                        for index in range(abs(shift)):
                            mute_locs[pos-st_ind+1+index] = ""
                    #print "reverse", str(end_ind-st_ind), str(shift), str(pos_in_codon)
                    (left_side, right_side) = (pos-st_ind, end_ind-pos)
                    (cds_list, mute_locs) = get_cds(trans_id, mute_posits, left_side, right_side, exon_dict, mute_locs)
                    if len(cds_list) != 0:
                        orig_seq = ""
                        for cds_stretch in cds_list:
                            (seq_start, seq_length) = cds_stretch
                            try:
                                orig_seq += get_seq(chrom, seq_start, seq_length, ref_ind)
                            except:
                                print(chrom, seq_start, seq_length)
                                break
                        try:
                            right_half = len(orig_seq)
                            orig_seq = find_stop(query_st, trans_id,
                                                  line_count, exon_dict, chrom,
                                                  ref_ind, mute_locs, True) + orig_seq
                            adjust_locs = dict()
                            for key in mute_locs:
                                adjust_key = key+len(orig_seq)-right_half
                                adjust_locs[adjust_key] = mute_locs[key]
                            mute_seq = make_mute_seq(orig_seq, adjust_locs)
                            wild_seq = get_seq(chrom, end_ind-len(mute_seq)+1, len(mute_seq), ref_ind)
                            kmer(mute_posits, turn_to_aa(wild_seq, "-"), turn_to_aa(mute_seq, "-"))
                            print "Reverse Indel ", wild_seq, "\t", mute_seq, len(wild_seq), len(mute_seq), pos
                        except:
                            (mute_locs, mute_posits, last_chrom) = (dict(), [], "None")
                            print "Reverse Failure"
                            break
                if strand == "+":
                    #print(len(mute_locs))
                    if(len(mute_locs)==0):
                        st_ind = pos-30-pos_in_codon
                    if len(alt) > len(orig):
                        #print "insertion"
                        #st_ind = pos - (30+pos_in_codon)
                        #st_ind = (2-(pos_in_codon + len(alt))%3) + pos + pos_in_codon + len(alt) + 30
                        #end_ind = pos + len(alt) - 1
                        end_ind = pos + 2 - (pos_in_codon+shift)%3
                        query_st = end_ind + 1
                        mute_locs[pos-st_ind] = alt
                    else:
                        #print "deletion"
                        #st_ind = 30 + pos_in_codon + pos +len(orig) - 1
                        #st_ind = (2-(pos_in_codon + len(alt))%3) + pos + pos_in_codon + len(alt) + 30
                        end_ind = pos + 2 - pos_in_codon + abs(shift)
                        query_st = end_ind + 1
                        for index in range(abs(shift)):
                            mute_locs[pos-st_ind+1+index] = ""
                    #print "forward ", str(end_ind-st_ind), str(shift), str(pos_in_codon)
                    (left_side, right_side) = (pos-st_ind, end_ind-pos)
                    (cds_list, mute_locs) = get_cds(trans_id, mute_posits, left_side, right_side, exon_dict, mute_locs)
                    if len(cds_list) != 0:
                        orig_seq = ""
                        for cds_stretch in cds_list:
                            (seq_start, seq_length) = cds_stretch
                            try:
                                orig_seq += get_seq(chrom, seq_start, seq_length, ref_ind)
                            except:
                                print(chrom, seq_start, seq_length)
                                break
                        try:
                            orig_seq += find_stop(query_st, trans_id,
                                                  line_count, exon_dict, chrom,
                                                  ref_ind, mute_locs, False)
                            '''missense_pos = pos
                            curr_line = line_count
                            while(missense_pos < (st_ind+len(orig_seq))):
                                try:
                                    new_line = next(input_stream)
                                except:
                                    pass
                                #new_line = input_stream[curr_line]
                                vals = new_line.strip().split('\t')
                                (missense_pos, alt, info) = (int(vals[1]), vals[4], vals[7]
                                    )
                                tokens = info.strip().split('|')
                                mute_type = tokens[1]
                                if(missense_pos >= st_ind+len(orig_seq)):
                                    break
                                if(mute_type != "missense_variant"): continue
                                seq_pos = missense_pos + shift - st_ind
                                mute_locs[seq_pos] = alt'''
                            mute_seq = make_mute_seq(orig_seq, mute_locs)
                            #print "Forward ", orig_seq, str(len(orig_seq)), str(len(mute_seq))
                            wild_seq = get_seq(chrom, st_ind, len(mute_seq), ref_ind)
                            kmer(mute_posits, turn_to_aa(wild_seq, "+"), turn_to_aa(mute_seq, "+"))
                            print "Indel ", wild_seq, "\t", mute_seq, len(wild_seq), len(mute_seq), pos
                        except:
                            (mute_locs, mute_posits, last_chrom) = (dict(), [], "None")
                            print("HERE DELIN")
                            pass
                        #NEED TO EDIT try-except so that the sequence upto the stop
                        # is included, and not breaks
                (mute_locs, mute_posits) = (dict(), [])
                last_chrom = "None"
                continue
            if last_chrom == chrom and pos-last_pos <= (32-pos_in_codon):
                #The order of that if-statement is important! Don't change it!
                end_ind = pos+32-pos_in_codon
            else:
                st_ind = pos-30-pos_in_codon
                end_ind = pos+32-pos_in_codon
            mute_locs[(pos-st_ind)] = alt
            mute_posits.append((pos, line_count))
            (last_pos,last_chrom) = (pos, chrom)
        (left_side,right_side) = (last_pos-st_ind,end_ind-last_pos)
        (cds_list,mute_locs) = get_cds(trans_id, mute_posits, left_side, right_side, my_dict, mute_locs)
        print("Final mute_locs: ", str(mute_locs), str(mute_posits))
        if(len(cds_list) != 0):
            find_seq_and_kmer(cds_list, last_chrom, ref_ind, mute_locs,
                              orf_dict, trans_id, mute_posits)

finally:
    if args.vcf != '-':
        input_stream.close()