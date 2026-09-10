MODULE MainModule
    !=====================================================================
    ! MainModule - the pick-and-place program.
    !
    ! Objects lie on the picking board at random, so every picking position
    ! comes from the vision server. Placing positions stay fixed.
    !
    !   operator types "circle red" at the server
    !   -> server finds it and sends  move circle 123.45 -45.30 -12.5#
    !   -> operator presses the yellow button
    !   -> robot picks there, places in the circle's slot
    !
    ! No code is written inside ServerCommuncatio.sys; it is only called.
    ! All coordinates, speeds and timings live in StationData.mod.
    !
    ! Author: Suraj Karki
    ! Course: INA700 - AI-based pick and place
    !=====================================================================

    ! One command from the server, after parsing.
    RECORD pickcommand
        num shapeIndex;
        num x;
        num y;
        num rotation;
    ENDRECORD

    !--- Entry point ------------------------------------------------------

    PROC main()
        PrepareCell;

        IF NOT OperatorConfirmsStart() THEN
            TPWrite "Cancelled by the operator.";
            RETURN;
        ENDIF

        RobotAsClientConnect;
        RunCommandLoop;
        RobotClientCloseAndDisconnect;
    ENDPROC

    ! Asks before opening the socket, so the cell is never left waiting on a
    ! connection nobody meant to start.
    FUNC bool OperatorConfirmsStart()
        VAR num answer;

        TPReadFK answer, "Connect to the vision server?", "Yes", stEmpty,
                 stEmpty, stEmpty, "Cancel";

        RETURN answer = 1;
    ENDFUNC

    PROC PrepareCell()
        TPErase;
        VacuumOff;

        ! Computed targets carry no taught arm configuration, so the checks
        ! must be off or the controller stops mid-board. Watch the first few
        ! picks and confirm the arm takes a sane posture.
        ConfL \Off;
        ConfJ \Off;

        MoveJ Phome, vTravel, fine, vac\WObj:=wobj1;
        TPWrite "Ready. Waiting for the vision server.";
    ENDPROC

    !--- Command loop -----------------------------------------------------

    PROC RunCommandLoop()
        VAR string command;
        VAR bool running := TRUE;

        WHILE running DO
            TPWrite "Waiting for a command...";
            command := RobotClientReciveMessage();
            running := HandleCommand(command);
        ENDWHILE
    ENDPROC

    ! Handles one message. Returns FALSE when the server asks us to stop.
    ! Failures return early, keeping the successful path flat.
    FUNC bool HandleCommand(string command)
        VAR pickcommand request;

        IF WordAt(command, 1) = QUIT_COMMAND THEN
            TPWrite "Quit received. Shutting down.";
            RETURN FALSE;
        ENDIF

        IF NOT ParseCommand(command, request) THEN
            TPWrite "Ignored unreadable command: " + command;
            RobotClienSendMessage ERROR_PREFIX + command + MESSAGE_END;
            RETURN TRUE;
        ENDIF

        IF NOT PickPointIsOnTheBoard(request) THEN
            TPWrite "Refused - the position is off the board: " + command;
            RobotClienSendMessage ERROR_PREFIX + "off board" + MESSAGE_END;
            RETURN TRUE;
        ENDIF

        RunPickCycle request;
        RETURN TRUE;
    ENDFUNC

    PROC RunPickCycle(pickcommand request)
        VAR string shapeName;

        shapeName := shapeNames{request.shapeIndex};

        TPWrite "Press the yellow button to pick the " + shapeName;
        WaitDI diOkButton, 1;
        WaitTime BUTTON_DEBOUNCE_TIME;

        PickAndPlace request;

        TPWrite "Placed the " + shapeName + ".";
        RobotClienSendMessage DONE_PREFIX + shapeName + MESSAGE_END;
    ENDPROC

    !--- Parsing ----------------------------------------------------------

    ! Reads "move <shape> <x> <y> <rz>". Shape, X and Y are required: with the
    ! objects placed at random there is no taught position to fall back on.
    FUNC bool ParseCommand(string command, INOUT pickcommand request)
        request.x := 0;
        request.y := 0;
        request.rotation := 0;

        request.shapeIndex := ShapeIndexOf(WordAt(command, 2));
        IF request.shapeIndex = 0 THEN
            RETURN FALSE;
        ENDIF

        IF NOT StrToVal(WordAt(command, 3), request.x) THEN
            RETURN FALSE;
        ENDIF
        IF NOT StrToVal(WordAt(command, 4), request.y) THEN
            RETURN FALSE;
        ENDIF

        ! Rotation may be omitted - a circle needs no turning.
        IF NOT StrToVal(WordAt(command, 5), request.rotation) THEN
            request.rotation := 0;
        ENDIF

        RETURN TRUE;
    ENDFUNC

    ! Fence around the picking board. With random positions a miscalibrated
    ! camera would otherwise be believed, and the robot would hit the fixture.
    FUNC bool PickPointIsOnTheBoard(pickcommand request)
        IF request.x < PICK_AREA_MIN_X OR request.x > PICK_AREA_MAX_X THEN
            RETURN FALSE;
        ENDIF
        IF request.y < PICK_AREA_MIN_Y OR request.y > PICK_AREA_MAX_Y THEN
            RETURN FALSE;
        ENDIF
        RETURN TRUE;
    ENDFUNC

    ! The n-th word of a message, counting from 1. '#' counts as a separator,
    ! so the terminator never sticks to the last value.
    FUNC string WordAt(string sentence, num wordNumber)
        VAR num searchFrom;
        VAR num separatorAt;
        VAR num wordsPassed;
        VAR num sentenceLength;

        searchFrom := 1;
        wordsPassed := 0;
        sentenceLength := StrLen(sentence);

        WHILE searchFrom <= sentenceLength + 1 DO
            ! StrFind returns sentenceLength + 1 when nothing is left.
            separatorAt := StrFind(sentence, searchFrom, WORD_SEPARATORS);
            Incr wordsPassed;

            IF wordsPassed = wordNumber THEN
                IF separatorAt <= searchFrom THEN
                    RETURN "";
                ENDIF
                RETURN StrPart(sentence, searchFrom, separatorAt - searchFrom);
            ENDIF

            searchFrom := separatorAt + 1;
        ENDWHILE

        RETURN "";
    ENDFUNC

    ! Index of a shape in the catalogue, or 0 when the name is not one of ours.
    FUNC num ShapeIndexOf(string shapeName)
        VAR string wanted;
        VAR num index;

        wanted := StrMap(shapeName, STR_UPPER, STR_LOWER);

        FOR index FROM 1 TO NUMBER_OF_SHAPES DO
            IF shapeNames{index} = wanted THEN
                RETURN index;
            ENDIF
        ENDFOR

        RETURN 0;
    ENDFUNC

    !--- Motion -----------------------------------------------------------

    PROC PickAndPlace(pickcommand request)
        VAR robtarget pickPoint;
        VAR robtarget placePoint;

        pickPoint := PickTargetFor(request);
        placePoint := PlaceTargetFor(request);

        MoveJ Phome, vTravel, fine, vac\WObj:=wobj1;
        MoveL Papproach, vTravel, fine, vac\WObj:=wobj1;

        MoveL Offs(pickPoint, 0, 0, APPROACH_HEIGHT_MM), vTravel, fine, vac\WObj:=wobj1;
        MoveL pickPoint, vApproach, fine, vac\WObj:=wobj1;
        WaitTime SETTLE_TIME;
        VacuumOn;
        MoveL Offs(pickPoint, 0, 0, APPROACH_HEIGHT_MM), vApproach, fine, vac\WObj:=wobj1;

        MoveL Offs(placePoint, 0, 0, APPROACH_HEIGHT_MM), vTravel, fine, vac\WObj:=wobj2;
        MoveL placePoint, vApproach, fine, vac\WObj:=wobj2;
        WaitTime SETTLE_TIME;
        VacuumOff;
        MoveL Offs(placePoint, 0, 0, APPROACH_HEIGHT_MM), vApproach, fine, vac\WObj:=wobj2;

        MoveJ Phome, vTravel, fine, vac\WObj:=wobj1;
    ENDPROC

    ! Where to pick. Every object is the same thickness and the cup comes
    ! straight down, so the pose does not depend on the shape - only X and Y
    ! change. Papproach supplies the tool orientation, already taught in wobj1.
    FUNC robtarget PickTargetFor(pickcommand request)
        VAR robtarget target;

        target := Papproach;
        target.trans.x := request.x;
        target.trans.y := request.y;
        target.trans.z := PICK_SURFACE_Z_MM;
        RETURN target;
    ENDFUNC

    ! Where to place. The taught target resolved against wobj2 is that shape's
    ! fixed slot. The wrist turns here, not at the pick, because a suction cup
    ! grips the object at whatever angle it was lying.
    !
    ! RelTool's whole signature is (Point, Dx, Dy, Dz [\Rx] [\Ry] [\Rz]) - there
    ! is no \Tool and no \WObj, and the controller rejects them. It needs
    ! neither: the rotation is applied about the axes of the POINT'S OWN
    ! orientation, so the frame comes from placeTargets{i} itself rather than
    ! from whatever happens to be active.
    !
    ! That orientation has the cup pointing down, so \Rz turns about the
    ! vertical - the wrist correction the vacuum pick makes necessary. Its
    ! sense follows the tool Z, which points downward; if a test object comes
    ! out turned the wrong way that is coordinates.angle_sign in config.yaml,
    ! not this line.
    FUNC robtarget PlaceTargetFor(pickcommand request)
        RETURN RelTool(placeTargets{request.shapeIndex}, 0, 0, 0 \Rz:=request.rotation);
    ENDFUNC

    !--- Gripper ----------------------------------------------------------

    PROC VacuumOn()
        Set doValve1;
        WaitTime GRIP_TIME;
    ENDPROC

    PROC VacuumOff()
        Reset doValve1;
        WaitTime RELEASE_TIME;
    ENDPROC

ENDMODULE
