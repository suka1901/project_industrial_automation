MODULE MessageParser(SYSMODULE)
    !=========================================================================
    ! MessageParser - turns one protocol string from the vision server into a
    ! structured command.
    !
    ! Incoming format (see message_codec.py):
    !     P,123.45,-45.30,0.00,37.5,STAR,RED#
    !     |    |       |     |    |    |    |
    !     |    x       y     z   Rz  shape colour
    !     command letter
    !
    ! A RAPID string holds 80 characters at most, which is why the protocol is
    ! this compact. Splitting is done with StrFind / StrPart / StrToVal.
    !=========================================================================

    ! One parsed command. Grouping the fields keeps every procedure signature
    ! short instead of passing six loose numbers around.
    RECORD pickcommand
        num x;
        num y;
        num z;
        num rotation;
        num shapeIndex;
        string colour;
    ENDRECORD

    !--- Public -----------------------------------------------------------

    FUNC bool ParseCommand(string message, INOUT pickcommand command)
        ! Fills 'command' from the received string.
        ! Returns FALSE and changes nothing meaningful if the string is not a
        ! well-formed pick command, so a garbled message can never move the
        ! robot to a fabricated position.

        IF StrLen(message) < 2 THEN
            RETURN FALSE;
        ENDIF

        IF StrPart(message, 1, 1) <> "P" THEN
            RETURN FALSE;
        ENDIF

        IF NOT NumberFromField(message, 2, command.x) THEN
            RETURN FALSE;
        ENDIF
        IF NOT NumberFromField(message, 3, command.y) THEN
            RETURN FALSE;
        ENDIF
        IF NOT NumberFromField(message, 4, command.z) THEN
            RETURN FALSE;
        ENDIF
        IF NOT NumberFromField(message, 5, command.rotation) THEN
            RETURN FALSE;
        ENDIF

        command.shapeIndex := ShapeIndexOf(FieldAt(message, 6));
        IF command.shapeIndex = 0 THEN
            RETURN FALSE;
        ENDIF

        command.colour := FieldAt(message, 7);
        RETURN TRUE;
    ENDFUNC

    FUNC num ShapeIndexOf(string name)
        ! Looks a shape name up in the catalogue. Returns 0 when unknown,
        ! which is how an unassigned shape gets rejected on the robot side too.
        VAR string upperName;
        VAR num index;

        upperName := StrMap(name, STR_LOWER, STR_UPPER);

        FOR index FROM 1 TO NUMBER_OF_SHAPES DO
            IF SHAPE_NAMES{index} = upperName THEN
                RETURN index;
            ENDIF
        ENDFOR

        RETURN 0;
    ENDFUNC

    !--- Internal ---------------------------------------------------------

    FUNC string FieldAt(string message, num fieldNumber)
        ! Returns the n-th separator-delimited field, counting from 1.
        ! Written once and reused for every field, so there is no repeated
        ! index arithmetic scattered through the parser.
        VAR num searchFrom;
        VAR num separatorAt;
        VAR num fieldsPassed;
        VAR num messageLength;

        searchFrom := 1;
        fieldsPassed := 0;
        messageLength := StrLen(message);

        WHILE searchFrom <= messageLength + 1 DO
            ! StrFind returns messageLength + 1 when no separator remains,
            ! which conveniently marks the end of the last field.
            separatorAt := StrFind(message, searchFrom, FIELD_SEPARATORS);
            Incr fieldsPassed;

            IF fieldsPassed = fieldNumber THEN
                IF separatorAt <= searchFrom THEN
                    RETURN "";
                ENDIF
                RETURN StrPart(message, searchFrom, separatorAt - searchFrom);
            ENDIF

            searchFrom := separatorAt + 1;
        ENDWHILE

        RETURN "";
    ENDFUNC

    FUNC bool NumberFromField(string message, num fieldNumber, INOUT num value)
        ! Reads one numeric field. Keeping the conversion in one place means
        ! the four coordinate fields are read identically and any change to
        ! the number format is a single edit.
        RETURN StrToVal(FieldAt(message, fieldNumber), value);
    ENDFUNC
ENDMODULE
