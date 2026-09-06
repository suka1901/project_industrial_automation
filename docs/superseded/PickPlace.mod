MODULE PickPlace(SYSMODULE)
    !=========================================================================
    ! PickPlace - all robot motion and gripper handling.
    !
    ! Every position is built with Offs from one of the two taught origins, so
    ! reprogramming either work object moves everything with it and nothing
    ! here has to change.
    !
    ! The gripper is a vacuum cup, which shapes the whole strategy: the robot
    ! picks STRAIGHT DOWN whatever angle the object lies at, and does all of
    ! its rotating at the placing end. That is why the received Rz is applied
    ! in PlaceInSlot and not in PickAt.
    !=========================================================================

    PROC ConnectSignals()
        ! The only place in the program that knows the controller's real I/O
        ! names. Find them under I/O on the teach pendant and change them here.
        !
        ! AliasIO <real controller signal>, <name used in this program>;
        AliasIO doVacuumCup, doVacuum;
        AliasIO diYellowButton, diStartButton;
        AliasIO diVacuumSwitch, diVacuumOK;
    ENDPROC

    PROC MoveToHome()
        MoveJ pHome, vTravel, z50, tVacuum;
    ENDPROC

    PROC MoveToApproach()
        MoveJ pApproach, vTravel, z50, tVacuum;
    ENDPROC

    !--- Gripper ----------------------------------------------------------

    PROC VacuumOn()
        Set doVacuum;
    ENDPROC

    PROC VacuumOff()
        Reset doVacuum;
    ENDPROC

    FUNC bool ObjectIsHeld()
        ! Asks the vacuum switch whether the cup actually sealed. This is what
        ! makes a retry meaningful: without it, a missed object is only
        ! discovered when the robot places nothing into the slot.
        IF NOT VACUUM_FEEDBACK_FITTED THEN
            RETURN TRUE;
        ENDIF

        RETURN diVacuumOK = 1;
    ENDFUNC

    !--- Picking ----------------------------------------------------------

    FUNC bool PickAt(num offsetX, num offsetY, num depth)
        ! Picks the object at the given offset from the picking origin.
        ! Returns FALSE when the cup failed to seal, so the caller can retry.
        VAR robtarget pickPoint;
        VAR robtarget abovePick;

        pickPoint := Offs(pPickOrigin, offsetX, offsetY, depth);
        abovePick := Offs(pickPoint, 0, 0, APPROACH_HEIGHT);

        MoveJ abovePick, vTravel, z20, tVacuum \WObj := wobjPick;
        MoveL pickPoint, vApproach, fine, tVacuum \WObj := wobjPick;

        VacuumOn;
        WaitTime GRIP_SETTLE_TIME;

        MoveL abovePick, vApproach, z10, tVacuum \WObj := wobjPick;

        RETURN ObjectIsHeld();
    ENDFUNC

    !--- Placing ----------------------------------------------------------

    PROC PlaceInSlot(num shapeIndex, num rotation)
        ! Places the held object in its designated slot, turning the wrist by
        ! 'rotation' so the object seats correctly.
        !
        ! 'rotation' arrives already reduced by the vision server into the
        ! shape's own symmetry: a square never turns more than 45 degrees and
        ! a circle always receives 0.
        VAR robtarget slotPoint;
        VAR robtarget aboveSlot;

        slotPoint := Offs(pPlaceOrigin, SLOT_OFFSET_X{shapeIndex},
                          SLOT_OFFSET_Y{shapeIndex}, 0);
        slotPoint := RelTool(slotPoint, 0, 0, 0 \Rz := rotation);
        aboveSlot := Offs(slotPoint, 0, 0, APPROACH_HEIGHT);

        MoveJ aboveSlot, vTravel, z20, tVacuum \WObj := wobjPlace;
        MoveL slotPoint, vApproach, fine, tVacuum \WObj := wobjPlace;

        VacuumOff;
        WaitTime RELEASE_TIME;

        MoveL aboveSlot, vApproach, z10, tVacuum \WObj := wobjPlace;
    ENDPROC

    !--- Operator ---------------------------------------------------------

    PROC WaitForStartButton()
        ! The yellow button starts every picking operation, in both modes.
        TPWrite "Press the yellow button to start picking.";
        WaitDI diStartButton, 1;
        WaitTime BUTTON_DEBOUNCE_TIME;
    ENDPROC
ENDMODULE
