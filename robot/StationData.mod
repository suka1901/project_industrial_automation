MODULE StationData
    !=====================================================================
    ! StationData - every value taught or measured on this cell.
    !
    ! Re-teaching the cell means editing this module and nothing else.
    ! Load it together with MainModule.mod: the old MainModule declared the
    ! same tool, work objects and targets, so both at once will not compile.
    !
    ! Signals diOkButton (yellow button) and doValve1 (vacuum) are configured
    ! in the controller I/O, so they are not declared here.
    !
    ! Author: Suraj Karki
    ! Course: INA700 - AI-based pick and place
    !=====================================================================

    !--- Tool -------------------------------------------------------------
    TASK PERS tooldata vac:=[TRUE,[[-90.2059,1.81102,177.839],[1,0,0,0]],
                             [0.5,[50,0,50],[1,0,0,0],0,0,0]];

    !--- Work objects -----------------------------------------------------
    ! wobj1 is the A3 sheet, the frame the camera measures in.
    ! wobj2 is the placing jig. Two work objects, as the assignment requires.
    ! Taught 2026-09-09. wobj1's origin is ON the corner of the A3 sheet with
    ! X along the 420 mm edge, which is why SHEET_ORIGIN below is 0,0.
    TASK PERS wobjdata wobj1:=[FALSE,TRUE,"",
        [[452.084,-294.953,-12.6039],
         [0.999985,-0.00286025,0.00463156,7.67918E-06]],
        [[0,0,0],[1,0,0,0]]];
    TASK PERS wobjdata wobj2:=[FALSE,TRUE,"",
        [[603.794,191.391,-1.66908],
         [0.999953,-0.00799821,-0.00134328,0.0052535]],
        [[0,0,0],[1,0,0,0]]];

    !--- Positions --------------------------------------------------------
    ! Five placing targets plus one approach and one home - exactly the budget
    ! the assignment allows.
    ! Taught 2026-09-09 against the wobj1 above.
    CONST robtarget Phome:=[[114.95,277.26,163.28],
        [0.00373083,0.00468543,-0.99993,0.0101865],[-1,-1,-1,0],
        [9E+09,9E+09,9E+09,9E+09,9E+09,9E+09]];

    ! Papproach is more than a waypoint: PickTargetFor copies it and overwrites
    ! only X, Y and Z, so its ORIENTATION is inherited by every computed pick.
    ! Measured 1.24 deg off straight down, which costs about 0.2 mm of lateral
    ! drift over a 10 mm descent. Re-teach it if the cup is ever remounted.
    CONST robtarget Papproach:=[[178.25,183.91,56.62],
        [0.00374539,0.00469495,-0.99993,0.0101858],[-1,-1,-1,0],
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
    VAR robtarget placeTargets{5} := [p10,p30,p40,p50,p60];

    !--- Picking height ---------------------------------------------------
    ! Height in wobj1 where the cup meets the top of an object. One value,
    ! because every object is the same thickness.
    !
    ! 10 mm is DERIVED, not taught: wobj1's Z=0 is the sheet surface and the
    ! objects are 10 mm thick, so the cup meets the top at 10. It errs safely
    ! in both directions - a millimetre high just fails to seal, a millimetre
    ! low presses slightly and seals better - but grip reliability is this
    ! figure, so confirm it on the first picks:
    !
    !   cup does not seal, object left behind  -> lower it 0.5 mm at a time
    !   cup presses hard, object shifts        -> raise it 0.5 mm at a time
    !
    ! Re-teach it properly if wobj1 is ever redefined.
    CONST num PICK_SURFACE_Z_MM := 10;

    !--- Picking area limits ----------------------------------------------
    ! The A3 sheet is the work surface. Objects are only ever picked from it,
    ! so the fence is the sheet plus a margin. Derived from one measured
    ! corner, so a re-taught wobj1 costs two numbers instead of four.
    !
    ! Zero by construction: wobj1 was defined with its origin ON the corner of
    ! the A3 sheet, X along the 420 mm edge. Nothing to measure, and the fence
    ! below is therefore exact rather than inherited from a jogged reading.
    ! If wobj1 is ever re-taught somewhere else, measure these two again.
    CONST num SHEET_ORIGIN_X := 0;
    CONST num SHEET_ORIGIN_Y := 0;

    ! A3 is 420 x 297 mm. Swap the two if the long edge runs along wobj1 Y.
    CONST num SHEET_SPAN_X := 420;
    CONST num SHEET_SPAN_Y := 297;

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
