We must make changes to the frontend (electron-app-v4) and the backends (python fastapi AND electron v4 api):
- When we do Batch Processing, we want to be able to fill in a number of fields, atm, namely: 1. Veranstaltungsnummer, 2. Datum, 3. Veranstaltungstitel, 4. Urheber, 5. Fachbereich
- For all of these, we must be able to select from a dropdown already existing options and enter new ones. For (5.) Fachbereich, we need the following predefined: DIR, ÖFA, GES, GUS, HOH, INZ, IRD, MMN, NUT, KUN, RSP, SUG.
- When we process a batch, we have the option to COPY or MOVE (or leave at is) the files to a predefined path (namely, as default /mnt/bildarchiv/Fachbereich(one of the above shorthands)/Year/Veranstaltungstitel/(Filename:)(Fachbereich_Veranstaltungsnummer_Datum_Description_counter).extension
in the form of e.g. /mnt/bildarchiv/IRD/2025/Theologisches Forum/IRD_54321_2025_03_Ströbele_Hamdan_Podium_001.jpg
where the Description would be made up of the Lastnames of the persons on the picture, in this case, Christian Ströbele and Hussein Hamdan.
- We set this filename after we identified the persons. 
- Also, we need a new function for the multi-select-tool (upper toolbar): Als Unterauswahl ablegen. (right of it, a small dropdown opening chevron to choose from: MOVE/COPY) ==> when hit, we copy or move the selected files to a chosen destination, in this case: /mnt/bildauswahl/
where we build the path and filename by the same logic, per default: /mnt/bildauswahl/IRD/2025/Theologisches Forum/IRD_54321_2025_03_Ströbele_Hamdan_001.jpg
So, we use Fachbereichsnummer_Veranstaltungsnummer_DateYear_DateMonth_Name(s)(or Short Description)_counter.ext
- We need also the option to RE-NAME/RE-SORT individual images, in case we changed the identifications. Also from this multi-select-tool.
- We also store these metadata into the file metadata fields, where possible, e.g. this must be mostly possible for JPG metadata fields. Optionally, we create JPG files for each image which was not initially a JPG. On rename, we also update the EXIF/XMP-fields.
- These fields and path building logics must be predefined as above. But *Admins* must be able to change them, in the UI: they can set the predefined storage path, set the predefined choices for fields, set the fieldnames (add and remove from them, up to 10), set their order in the UI, set the logic how we build the folder path and full filename, both for the "normal" Bildarchiv, and for the "Bildauswahl"-Archive (separately, but with an option to copy from one to the other the definition). Here we also need the option whether to, per default, also create JPGs, if not already as jpg, AND a mapping of the Admin-defined metadata-fields to the JPG-EXIF/IPTC/XMP-metadata-fields. The defaults shall be:
1. Veranstaltungsnummer = (2nd part of XPSubject=dc.title)
2. Datum = EXIF-RecordingDate = xmp.CreateDate
3. Veranstaltungstitel = (3rd part of XPSubject=dc.title)
4. Urheber = XP Copyright = dc.rights
5. Fachbereich = (1st part of XPSubject=dc.title)
(6.) Tags = XPKeywords = dc.subject[n] = LastKeywordXMP[n]
(7.) Description = XPComment
(8.) Personen = XPKeywords = dc.subject[n] = LastKeywordXMP[n]
So, e.g., the XPSubject would become IRD_54321_Theologisches Forum
- in the DB, we must store the original path of an image, and, if possible, the new (overriding) Bildarchiv path, and, if possible, also the new Bildauswahl path
- when we attempt to OPEN a fullsize version of an image, we have this order of priority / fallback logic: Bildarchiv-Path, Bildauswahl-Path, Original-Path, Thumbnail-in-DB.
