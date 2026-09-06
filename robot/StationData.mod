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
    TASK PERS wobjdata wobj1:=[FALSE,TRUE,"",
        [[610.644,-338.06,2.86545],[0.999893,-0.012613,0.00614853,0.00412147]],
        [[0,0,0],[1,0,0,0]]];
    TASK PERS wobjdata wobj2:=[FALSE,TRUE,"",
        [[606.487,221.202,2.06637],[0.999954,0.00362135,0.00617943,0.00640069]],
        [[0,0,0],[1,0,0,0]]];

    !--- Positions --------------------------------------------------------
    ! Five placing targets plus one approach and one home - exactly the budget
    ! the assignment allows.
    CONST robtarget Phome:=[[-62.06,293.24,107.36],
        [0.0144604,0.110376,-0.993465,-0.0252167],[-1,0,-1,0],
        [9E+09,9E+09,9E+09,9E+09,9E+09,9E+09]];
    CONST robtarget Papproach:=[[-0.67,336.45,29.81],
        [0.014461,0.110376,-0.993465,-0.0252119],[-1,0,-1,0],
        [9E+09,9E+09,9E+09,9E+09,9E+09,9E+09]];

    CONST robtarget p10:=[[30.12,28.62,-0.23],
        [0.0144628,0.110404,-0.993463,-0.0251784],[-1,-1,-1,0],
        [9E+09,9E+09,9E+09,9E+09,9E+09,9E+09]];
    CONST robtarget p30:=[[153.79,26.47,3.87],
        [0.0144558,0.110389,-0.993464,-0.0251888],[-1,-1,-1,0],
        [9E+09,9E+09,9E+09,9E+09,9E+09,9E+09]];
    CONST robtarget p40:=[[38.30,150.06,3.11],
        [0.0144435,0.110374,-0.993466,-0.0251758],[-1,0,-1,0],
        [9E+09,9E+09,9E+09,9E+09,9E+09,9E+09]];
    CONST robtarget p50:=[[150.69,135.56,5.20],
        [0.0145033,0.110326,-0.993469,-0.0252387],[-1,0,-1,0],
        [9E+09,9E+09,9E+09,9E+09,9E+09,9E+09]];
    CONST robtarget p60:=[[91.66,86.91,1.39],
        [0.0144915,0.110364,-0.993465,-0.0252398],[-1,0,-1,0],
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
    ! MEASURE THIS: teach one pick point with an object under the cup and
    ! replace the number. Grip reliability is this figure.
    CONST num PICK_SURFACE_Z_MM := 2.7;

    !--- Picking area limits ----------------------------------------------
    ! The A3 sheet is the work surface. Objects are only ever picked from it,
    ! so the fence is the sheet plus a margin. Derived from one measured
    ! corner, so a re-taught wobj1 costs two numbers instead of four.
    !
    ! MEASURE THIS: jog the tool tip to the sheet corner nearest wobj1's
    ! origin and read X and Y off the pendant.
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
