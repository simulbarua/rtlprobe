`timescale 1ns/1ps
module tb_axis_fifo;
    reg clk = 0;
    reg rst = 0;
    always #5 clk = ~clk;

    reg [15:0] s_data = 0;
    reg [1:0] s_keep = 0;
    reg s_valid = 0, s_last = 0, s_user = 0;
    reg [7:0] s_id = 0, s_dest = 0;
    wire s_ready;
    reg m_ready = 0, pause_req = 0;
    wire [15:0] m_data;
    wire [1:0] m_keep;
    wire m_valid, m_last, m_user, pause_ack;
    wire [7:0] m_id, m_dest;
    wire overflow, bad_frame, good_frame;
    wire [4:0] depth, committed_depth;

    axis_fifo #(
        .DEPTH(16), .DATA_WIDTH(16), .KEEP_ENABLE(1), .KEEP_WIDTH(2),
        .LAST_ENABLE(1), .ID_ENABLE(1), .ID_WIDTH(8), .DEST_ENABLE(1),
        .DEST_WIDTH(8), .USER_ENABLE(1), .USER_WIDTH(1), .RAM_PIPELINE(1),
        .OUTPUT_FIFO_ENABLE(0), .FRAME_FIFO(1), .DROP_OVERSIZE_FRAME(1),
        .DROP_BAD_FRAME(1), .DROP_WHEN_FULL(0), .MARK_WHEN_FULL(0),
        .USER_BAD_FRAME_VALUE(1), .USER_BAD_FRAME_MASK(1),
        .PAUSE_ENABLE(1), .FRAME_PAUSE(1)
    ) dut (
        .clk(clk), .rst(rst), .s_axis_tdata(s_data), .s_axis_tkeep(s_keep),
        .s_axis_tvalid(s_valid), .s_axis_tready(s_ready), .s_axis_tlast(s_last),
        .s_axis_tid(s_id), .s_axis_tdest(s_dest), .s_axis_tuser(s_user),
        .m_axis_tdata(m_data), .m_axis_tkeep(m_keep), .m_axis_tvalid(m_valid),
        .m_axis_tready(m_ready), .m_axis_tlast(m_last), .m_axis_tid(m_id),
        .m_axis_tdest(m_dest), .m_axis_tuser(m_user), .pause_req(pause_req),
        .pause_ack(pause_ack), .status_depth(depth), .status_depth_commit(committed_depth),
        .status_overflow(overflow), .status_bad_frame(bad_frame), .status_good_frame(good_frame)
    );

    integer checked = 0, mismatches = 0, index;

    task step;
        begin
            @(posedge clk);
            #1;
        end
    endtask

    task reset_fifo;
        begin
            @(negedge clk);
            rst = 1;
            s_valid = 0;
            m_ready = 0;
            pause_req = 0;
            repeat (2) step;
            @(negedge clk);
            rst = 0;
            step;
        end
    endtask

    task send;
        input [15:0] data;
        input [1:0] keep;
        input last, user;
        integer cycles;
        begin : bounded_send
            @(negedge clk);
            s_data = data;
            s_keep = keep;
            s_last = last;
            s_user = user;
            s_id = 8'h39;
            s_dest = 8'ha6;
            s_valid = 1;
            for (cycles = 0; cycles < 20; cycles = cycles + 1) begin
                @(posedge clk);
                if (s_ready === 1'b1) begin
                    #1;
                    s_valid = 0;
                    disable bounded_send;
                end
            end
            $display("FIFO ABORT input_handshake");
            $finish;
        end
    endtask

    task read_one;
        begin
            @(negedge clk);
            m_ready = 1;
            step;
            m_ready = 0;
        end
    endtask

    task begin_check;
        input [8*48-1:0] id;
        $display("FIFO BEGIN %0s", id);
    endtask

    task check_sample;
        input [8*48-1:0] id;
        input [31:0] expected, actual;
        begin
            $display("FIFO RESULT %0s expected=%08h actual=%08h", id, expected, actual);
            checked = checked + 1;
            if (actual !== expected)
                mismatches = mismatches + 1;
        end
    endtask

    initial begin
        #1;
        $display("FIFO START v1");
        begin_check("uncommitted_hidden");
        reset_fifo;
        send(16'h51a3, 2'b11, 0, 1);
        repeat (4) step;
        check_sample("uncommitted_hidden", 0, m_valid);

        begin_check("commit_pulse");
        send(16'h0097, 2'b01, 1, 0);
        check_sample("commit_pulse", 1, good_frame);

        begin_check("stalled_valid");
        repeat (4) step;
        check_sample("stalled_valid", 1, m_valid);
        begin_check("stalled_data");
        repeat (3) step;
        check_sample("stalled_data", 32'h51a3, m_data);
        begin_check("first_not_last");
        check_sample("first_not_last", 0, m_last);
        begin_check("id_forwarded");
        check_sample("id_forwarded", 32'h39, m_id);
        begin_check("dest_forwarded");
        check_sample("dest_forwarded", 32'ha6, m_dest);
        begin_check("user_forwarded");
        check_sample("user_forwarded", 1, m_user);
        begin_check("second_data");
        read_one;
        check_sample("second_data", 32'h97, m_data);
        begin_check("partial_keep");
        check_sample("partial_keep", 1, m_keep);
        begin_check("final_last");
        check_sample("final_last", 1, m_last);

        begin_check("bad_frame_pulse");
        reset_fifo;
        send(16'h1234, 2'b11, 0, 0);
        send(16'h5678, 2'b11, 1, 1);
        check_sample("bad_frame_pulse", 1, bad_frame);
        begin_check("bad_frame_hidden");
        repeat (4) step;
        check_sample("bad_frame_hidden", 0, m_valid);

        begin_check("oversize_pulse");
        for (index = 0; index < 9; index = index + 1)
            send(16'h7000 + index, 2'b11, index == 8, 0);
        check_sample("oversize_pulse", 1, overflow);
        begin_check("oversize_hidden");
        repeat (4) step;
        check_sample("oversize_hidden", 0, m_valid);
        begin_check("rollback_recovers");
        send(16'h14d9, 2'b11, 1, 0);
        repeat (4) step;
        check_sample("rollback_recovers", 32'h14d9, m_data);

        begin_check("pause_deferred");
        reset_fifo;
        send(16'h3111, 2'b11, 0, 0);
        send(16'h3222, 2'b11, 1, 0);
        send(16'h4333, 2'b11, 1, 0);
        repeat (4) step;
        @(negedge clk);
        pause_req = 1;
        read_one;
        check_sample("pause_deferred", 0, pause_ack);
        begin_check("pause_at_boundary");
        read_one;
        check_sample("pause_at_boundary", 1, pause_ack);
        begin_check("pause_valid_suppressed");
        step;
        check_sample("pause_valid_suppressed", 0, m_valid);
        begin_check("resume_valid");
        @(negedge clk);
        pause_req = 0;
        step;
        check_sample("resume_valid", 1, m_valid);

        begin_check("reset_discards_queued");
        reset_fifo;
        repeat (4) step;
        check_sample("reset_discards_queued", 0, m_valid);
        begin_check("reset_discards_partial");
        send(16'h5678, 2'b11, 0, 0);
        reset_fifo;
        repeat (4) step;
        check_sample("reset_discards_partial", 0, committed_depth);
        begin_check("reset_accepts_clean_frame");
        send(16'h9812, 2'b11, 1, 0);
        repeat (4) step;
        check_sample("reset_accepts_clean_frame", 32'h9812, m_data);

        begin_check("wrap_preserves_data");
        read_one;
        for (index = 0; index < 18; index = index + 1) begin
            send(16'h81ff + index, 2'b11, 1, 0);
            repeat (4) step;
            read_one;
        end
        send(16'h772c, 2'b11, 1, 0);
        repeat (4) step;
        check_sample("wrap_preserves_data", 32'h772c, m_data);
        $display("FIFO END checked=%0d mismatches=%0d", checked, mismatches);
        $finish;
    end
endmodule
