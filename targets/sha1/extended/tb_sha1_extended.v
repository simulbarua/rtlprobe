// RTLProbe's SHA-1 core regression bench. The DUT receives pre-padded blocks.
// Compare the public digest after each selected transaction on a falling edge.
`timescale 1ns/1ps
`default_nettype none
module tb_sha1_extended;
  reg clk = 0;
  reg reset_n = 1;
  reg init = 0;
  reg next_block = 0;
  reg [511:0] block = 0;
  wire ready;
  wire valid;
  wire [159:0] digest;
  integer failures = 0;
  integer checks = 0;

  sha1_core dut(.clk(clk), .reset_n(reset_n), .init(init), .next(next_block),
                .block(block), .ready(ready), .digest(digest), .digest_valid(valid));
  always #1 clk = !clk;

  task reset_core;
    begin
      @(negedge clk);
      reset_n = 0;
      repeat (2) @(negedge clk);
      reset_n = 1;
    end
  endtask

  task launch_block(input first, input [511:0] data);
    begin
      @(negedge clk);
      if (ready !== 1'b1) begin
        $display("SHA1 INCOMPLETE: core was not ready for a command");
        $finish;
      end
      init = first;
      next_block = !first;
      block = data;
      @(negedge clk);
      init = 0;
      next_block = 0;
      block = 0; // Only the sampled block belongs to this transaction.
    end
  endtask

  task hash_block(input first, input [511:0] data);
    integer cycles;
    begin
      launch_block(first, data);
      // The pinned core documents 82 clocks per block. Sample on falling
      // edges so that registered outputs have settled after the rising edge.
      cycles = 0;
      while (ready === 1'b0 && cycles < 82) begin
        @(negedge clk);
        cycles = cycles + 1;
      end
      if (ready !== 1'b1 || valid !== 1'b1) begin
        $display("SHA1 INCOMPLETE: block did not produce a valid digest");
        $finish;
      end
    end
  endtask

  task begin_check(input [8*32-1:0] id);
    begin
      $display("SHA1 BEGIN %0s", id);
    end
  endtask

  task check_digest(input [8*32-1:0] id, input [159:0] expected);
    begin
      $display("SHA1 DIGEST %0s expected=%040h actual=%040h", id, expected, digest);
      if (digest !== expected)
        failures = failures + 1;
      checks = checks + 1;
    end
  endtask

  initial begin
    reset_core();

    // Published single-block message abc.
    begin_check("tc1");
    hash_block(1'b1, 512'h61626380000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000018);
    check_digest("tc1", 160'ha9993e364706816aba3e25717850c26c9cd0d89d);

    // Published two-block message, with separate first and final comparisons.
    begin_check("tc2_block1");
    hash_block(1'b1, 512'h6162636462636465636465666465666765666768666768696768696a68696a6b696a6b6c6a6b6c6d6b6c6d6e6c6d6e6f6d6e6f706e6f70718000000000000000);
    check_digest("tc2_block1", 160'hf4286818c37b27ae0408f581846771484a566572);
    begin_check("tc2_block2");
    hash_block(1'b0, 512'h000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001c0);
    check_digest("tc2_block2", 160'h84983e441c3bd26ebaae4aa1f95129e5e54670f1);

    // Start an empty message immediately after the previous digest.
    begin_check("empty");
    hash_block(1'b1, 512'h80000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000);
    check_digest("empty", 160'hda39a3ee5e6b4b0d3255bfef95601890afd80709);

    // 55 ascending bytes fill the last single-block message before padding spills.
    begin_check("boundary55");
    hash_block(1'b1, 512'h000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f202122232425262728292a2b2c2d2e2f303132333435368000000000000001b8);
    check_digest("boundary55", 160'h8ae2d46729cfe68ff927af5eec9c7d1b66d65ac2);

    // 128 patterned binary bytes require two data blocks and a separate padding block.
    begin_check("chain128");
    hash_block(1'b1, 512'h135ca5ee3780c9125ba4ed367fc8115aa3ec357ec71059a2eb347dc60f58a1ea337cc50e57a0e9327bc40d569fe8317ac30c559ee73079c20b549de62f78c10a);
    hash_block(1'b0, 512'h539ce52e77c009529be42d76bf08519ae32c75be075099e22b74bd064f98e12a73bc054e97e02972bb044d96df2871ba034c95de2770b9024b94dd266fb8014a);
    hash_block(1'b0, 512'h80000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000400);
    check_digest("chain128", 160'h3d2a6087b753ee344b2449332fcde215c5cf71af);

    // Interrupt an in-flight compression, reset, and hash a fresh binary message.
    launch_block(1'b1, {16{32'hdeadbeef}});
    repeat (11) @(negedge clk);
    reset_core();
    begin_check("restart");
    hash_block(1'b1, 512'h8000ff7f800000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020);
    check_digest("restart", 160'h9a2a451f5dff77fb0733b36f32b5e640ff67a0f5);

    $display("SHA1 DONE checks=%0d failures=%0d", checks, failures);
    $finish;
  end
endmodule
