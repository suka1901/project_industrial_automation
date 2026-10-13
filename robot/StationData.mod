MODULE StationData
    !=====================================================================
    ! StationData - every value taught or measured on this cell.    !
    ! Author: Suraj Karki
    ! Course: INA700 - AI-based pick and place
    !=====================================================================

    !--- Tool -------------------------------------------------------------
    TASK PERS tooldata vac:=[TRUE,[[-90.2059,1.81102,177.839],[1,0,0,0]],
                             [0.5,[50,0,50],[1,0,0,0],0,0,0]];

    !--- Work objects -----------------------------------------------------
    ! wobj1 is the A3 sheet, the frame the camera measures in.
    ! wobj2 is the placing jig. Two work objects, as the assignment requires.
    ! wobj1's origin is ON the corner of the A3 sheet nearest the robot,
    ! with X along the SHORT (297 mm) edge and Y along the long one, which is
    ! why SHEET_ORIGIN below is 0,0. Taught with the 3-point method using the
    ! pointer, not the cup - see LAB.md step 4.1 for why that matters.
    TASK PERS wobjdata wobj1:=[FALSE,TRUE,"",
        [[397.447,-311.276,-10.5054],
         [0.999885,-0.000441221,0.004406,0.0144727]],
        [[0,0,0],[1,0,0,0]]];
    TASK PERS wobjdata wobj2:=[FALSE,TRUE,"",
        [[603.794,191.391,-1.66908],
         [0.999953,-0.00799821,-0.00134328,0.0052535]],
        [[0,0,0],[1,0,0,0]]];

    !--- Positions --------------------------------------------------------
    ! Five placing targets plus one approach and one home - exactly the budget
    ! the assignment allows.
    ! Taught 2026-09-09 against the wobj1 above.
    CONST robtarget Phome:=[[114.94,-21.70,161.55],
        [0.00374677,0.00469629,-0.99993,0.0101852],[-1,-1,-1,0],
        [9E+09,9E+09,9E+09,9E+09,9E+09,9E+09]];

    ! Papproach is more than a waypoint: PickTargetFor copies it and overwrites
    ! only X, Y and Z, so its ORIENTATION is inherited by every computed pick.
    ! Measured 1.24 deg off straight down, which costs about 0.2 mm of lateral
    ! drift over a 10 mm descent. Re-teach it if the cup is ever remounted.
    CONST robtarget Papproach:=[[78.84,-26.27,60.01],
        [0.0108222,0.013101,-0.999789,0.0115253],[-1,-1,-1,0],
        [9E+09,9E+09,9E+09,9E+09,9E+09,9E+09]];

    ! Taught 2026-09-09 at the jig, but WITH WOBJ1 ACTIVE, then converted into
    ! wobj2 - which is what MainModule places against. The conversion goes via
    ! base coordinates and is exact: the robot multiplies by wobj2 again at run
    ! time, so each target lands on the same physical slot that was taught, and
    ! any error in wobj2 itself cancels rather than accumulating.
    ! Used as wobj2 values without converting, they would have been about
    ! 490 mm from the jig.
    CONST robtarget p10:=[[28.38,38.47,3.37],
        [0.009800,-0.000384,-0.999939,0.005030],[0,-1,0,0],
        [9E+09,9E+09,9E+09,9E+09,9E+09,9E+09]];
    CONST robtarget p30:=[[158.57,32.35,4.50],
        [0.009803,-0.000374,-0.999939,0.005041],[0,-1,0,0],
        [9E+09,9E+09,9E+09,9E+09,9E+09,9E+09]];
    ! Triangle duplicates the square's slot. Harmless - the server only ever
    ! sends circle, square and star - but the array must hold five valid
    ! targets to compile, and a duplicate is safer than an untaught one.
    CONST robtarget p40:=[[28.38,38.47,3.37],
        [0.009801,-0.000385,-0.999939,0.005030],[0,-1,0,0],
        [9E+09,9E+09,9E+09,9E+09,9E+09,9E+09]];
    CONST robtarget p50:=[[152.52,142.87,3.22],
        [0.009816,-0.000409,-0.999938,0.005033],[0,-1,0,0],
        [9E+09,9E+09,9E+09,9E+09,9E+09,9E+09]];
    CONST robtarget p60:=[[94.63,91.25,4.54],
        [0.009821,-0.000396,-0.999938,0.005040],[0,-1,0,0],
        [9E+09,9E+09,9E+09,9E+09,9E+09,9E+09]];

    !--- Object catalogue -------------------------------------------------
    ! Index i in shapeNames is index i in placeTargets. Lower case, as sent.
    CONST num NUMBER_OF_SHAPES := 5;
    CONST string shapeNames{5} := ["square","circle","triangle","hexagon","star"];

    ! PLACING targets only. Resolved against wobj2 each one is that shape's
    ! fixed slot. Picking positions come from the camera, not from here.
    ! CONST, not VAR. A VAR's initial value is evaluated once when the module
    ! is loaded and then KEPT: re-teaching p10-p60 would leave the array
    ! holding the old copies until someone reset the program pointer, and the
    ! robot would keep placing at last week's slots while the file on screen
    ! showed the new ones.
    CONST robtarget placeTargets{5} := [p10,p30,p40,p50,p60];

    !--- Picking height ---------------------------------------------------
    ! Height in wobj1 where the cup meets the top of an object.
    !
    ! RE-CHECK THIS. wobj1 was re-taught with the pointer, and the 3-point
    ! method puts Z=0 at the plane the three points were touched on. This
    ! value was tuned against the previous wobj1, so it is wrong by whatever
    ! the two datums differ by. Test on a scrap object before a real cycle.
    CONST num PICK_SURFACE_Z_MM := 10;

    !--- Picking area limits ----------------------------------------------
    ! The A3 sheet is the work surface. Objects are only ever picked from it,
    ! so the fence is the sheet plus a margin. Derived from one measured
    ! corner, so a re-taught wobj1 costs two numbers instead of four.
    !
    ! Zero by construction: wobj1 was defined with its origin ON the corner of
    ! the A3 sheet. Nothing to measure, and the fence below is therefore exact
    ! rather than inherited from a jogged reading.
    ! If wobj1 is ever re-taught somewhere else, measure these two again.
    CONST num SHEET_ORIGIN_X := 0;
    CONST num SHEET_ORIGIN_Y := 0;

    ! A3 is 420 x 297 mm, and the LONG edge runs along wobj1 Y here: X is the
    ! 297 mm short edge. These must agree with sheet.span_xy_mm in the Pi's
    ! config.yaml - they are the same rectangle described twice. When they
    ! disagree the symptom is one-sided: objects past the shorter fence are
    ! refused with "off the board" while everything nearer the origin picks
    ! normally, which reads like a vision fault and is not one.
    CONST num SHEET_SPAN_X := 297;
    CONST num SHEET_SPAN_Y := 420;

    ! Covers camera error and the sheet not lying exactly where it was taught.
    CONST num SHEET_MARGIN_MM := 15;

    CONST num PICK_AREA_MIN_X := SHEET_ORIGIN_X - SHEET_MARGIN_MM;
    CONST num PICK_AREA_MAX_X := SHEET_ORIGIN_X + SHEET_SPAN_X + SHEET_MARGIN_MM;
    CONST num PICK_AREA_MIN_Y := SHEET_ORIGIN_Y - SHEET_MARGIN_MM;
    CONST num PICK_AREA_MAX_Y := SHEET_ORIGIN_Y + SHEET_SPAN_Y + SHEET_MARGIN_MM;

    !--- Motion -----------------------------------------------------------
    CONST num APPROACH_HEIGHT_MM := 20;   ! clearance above a pick or place point
    CONST num SETTLE_TIME := 0.5;         ! pause before the cup touches down
    CONST num GRIP_TIME := 0.5;           ! time for the cup to seal
    CONST num RELEASE_TIME := 0.5;        ! time for the vacuum to break
    CONST num BUTTON_DEBOUNCE_TIME := 0.3;

    CONST speeddata vTravel := v200;
    CONST speeddata vApproach := v200;    ! lower if needed

    !--- Protocol ---------------------------------------------------------
    ! Must match pi/adapters/comms/message_codec.py.
    !   server -> robot   move circle 123.45 -45.30 -12.5#   /   quit#
    !   robot  -> server  DONE: circle#   /   ERROR: unknown shape 'blob'#
    ! '#' ends a message, so two replies in one TCP read stay separable.
    CONST string QUIT_COMMAND := "quit";
    CONST string DONE_PREFIX := "DONE: ";
    CONST string ERROR_PREFIX := "ERROR: ";
    CONST string MESSAGE_END := "#";
    CONST string WORD_SEPARATORS := " #";
ENDMODULE
