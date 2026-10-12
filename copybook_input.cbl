       

	   01 TAX-SPS-DTL.
            05 TAX-CODE-PRTY             PIC X(20)     VALUE SPACES.
            05 TAX-SEQ-CNTR              PIC 9(08)     VALUE ZEROES.
            05 TAX-AFP-DATA.
               10 TAX-LNFRMTYP           PIC X(06)    VALUE SPACES.
               10 TAX-REC-TP-DTL         PIC X(02)    VALUE 'SA'.
               10 TAX-MRK-INDS.
                  15 TAX-READ-VRFY       PIC X         VALUE '1'.
                  15 TAX-DMND-FEED       PIC X         VALUE '0'.
                  15 TAX-END-SET         PIC X         VALUE '1'.
                  15 TAX-INSERTS         PIC X(04)    VALUE '0'.
                  15 TAX-ENVLP-MRKNG     PIC X        VALUE '0'.
                  15 TAX-DVRT-SEAL       PIC X        VALUE '0'.
                  15 TAX-DVRT-UNSEAL     PIC X        VALUE '0'.
                  15                     PIC X(04)    VALUE '0010'.
                  15 TAX-PAGE-CNTR       PIC X(01)    VALUE '1'.
                  15                     PIC X(01)    VALUE '0'.
               10 TAX-DTL-SEQ-NMBR       PIC 9(06)    VALUE ZEROES.
               10 TAX-FILLER             PIC X(20)    VALUE SPACES.
            05 TAX-DTL-DATA-GRP.
               10 TAX-DTL-DATA-LNGTH     PIC 9(04)    VALUE ZEROES.
               10 TAX-PRI-INDX           PIC 9(04)    VALUE ZEROES.
               10 TAX-DEPT-CODE          PIC X(03)    VALUE SPACES.
               10 FILLER                 PIC X(06)    VALUE SPACES.
			   10 TAX-TEST-OCCURS   4 TIMES.
			      15  TAX-TYPE           PIC X(3)     VALUE SPACES.