`timescale 1ns/1ns

module tb_aes_extended;
  localparam HALF_PERIOD = 5;
  localparam MAX_CYCLES = 128;
  localparam AES128 = 1'b0, AES256 = 1'b1;
  localparam ENCRYPT = 1'b1, DECRYPT = 1'b0;

  // NIST SP 800-38A F.1 ECB examples and the AES-128 example in FIPS 197.
  // The core takes AES-128 keys in the high half of the key port.
  localparam [255:0] KEY128 = {128'h2b7e151628aed2a6abf7158809cf4f3c, 128'b0};
  localparam [255:0] KEY256 = 256'h603deb1015ca71be2b73aef0857d77811f352c073b6108d72d9810a30914dff4;
  localparam [255:0] REKEY128 = {128'h000102030405060708090a0b0c0d0e0f, 128'b0};
  localparam [127:0] P1 = 128'h6bc1bee22e409f96e93d7e117393172a;
  localparam [127:0] P2 = 128'hae2d8a571e03ac9c9eb76fac45af8e51;
  localparam [127:0] P3 = 128'h30c81c46a35ce411e5fbc1191a0a52ef;
  localparam [127:0] C128_1 = 128'h3ad77bb40d7a3660a89ecaf32466ef97;
  localparam [127:0] C128_2 = 128'hf5d3d58503b9699de785895a96fdbaaf;
  localparam [127:0] C128_3 = 128'h43b1cd7f598ece23881b00e3ed030688;
  localparam [127:0] C256_1 = 128'hf3eed1bdb5d2a03c064b5a7e3db181f8;
  localparam [127:0] C256_2 = 128'h591ccb10d410ed26dc5ba74a31362870;
  localparam [127:0] C256_3 = 128'hb6ed21b99ca6f4f9f153e7b1beafed1d;
  localparam [127:0] REKEY_P = 128'h00112233445566778899aabbccddeeff;
  localparam [127:0] REKEY_C = 128'h69c4e0d86a7b0430d8cdb78070b4c55a;

  reg clk, reset_n, init, next, encdec, keylen;
  reg [255:0] key;
  reg [127:0] block;
  wire ready, result_valid;
  wire [127:0] result;
  integer checked, mismatches;
  reg [8*32-1:0] active_checkpoint;

  aes_core dut(.clk(clk), .reset_n(reset_n), .encdec(encdec), .init(init), .next(next),
               .ready(ready), .key(key), .keylen(keylen), .block(block),
               .result(result), .result_valid(result_valid));

  always #HALF_PERIOD clk = ~clk;

  // Native qualification archives this VCD. Observational capture uses its own writer.
  initial begin
    $dumpfile("tb_aes_extended.vcd");
    $dumpvars(0, tb_aes_extended);
  end

  task terminal_failure;
    input [8*32-1:0] phase, signal_name;
    input expected_bit, actual_bit;
    begin
      $display("AES_EXT TERMINAL %0s %0s %0s expected=%b actual=%b", active_checkpoint, phase, signal_name, expected_bit, actual_bit);
      $display("AES_EXT STOP checked=%0d mismatches=%0d", checked, mismatches);
      $finish;
    end
  endtask

  task expect_handshake;
    input [8*32-1:0] phase;
    input expected_ready, expected_valid;
    begin
      if (ready !== expected_ready)
        terminal_failure(phase, "ready", expected_ready, ready);
      else if (result_valid !== expected_valid)
        terminal_failure(phase, "result_valid", expected_valid, result_valid);
    end
  endtask

  task start_init;
    input width;
    input [255:0] new_key;
    begin
      @(negedge clk);
      if (ready !== 1'b1)
        terminal_failure("before_init", "ready", 1'b1, ready);
      keylen = width;
      key = new_key;
      init = 1'b1;
      @(posedge clk); #1;
      expect_handshake("init_accepted", 1'b0, 1'b0);
      @(negedge clk);
      init = 1'b0;
    end
  endtask

  task start_block;
    input mode;
    input [127:0] value;
    begin
      @(negedge clk);
      if (ready !== 1'b1)
        terminal_failure("before_next", "ready", 1'b1, ready);
      encdec = mode;
      block = value;
      next = 1'b1;
      @(posedge clk); #1;
      expect_handshake("next_accepted", 1'b0, 1'b0);
      @(negedge clk);
      next = 1'b0;
    end
  endtask

  task wait_ready;
    input expect_result;
    integer cycles;
    begin
      cycles = 0;
      while (ready === 1'b0 && cycles < MAX_CYCLES) begin
        @(posedge clk); #1;
        cycles = cycles + 1;
        if (ready === 1'b0)
          expect_handshake("while_busy", 1'b0, 1'b0);
      end
      if (ready === 1'b0) begin
        if (expect_result)
          terminal_failure("block_cycle_limit", "ready", 1'b1, ready);
        else
          terminal_failure("key_expansion_cycle_limit", "ready", 1'b1, ready);
      end
      expect_handshake("completion", 1'b1, expect_result);
    end
  endtask

  task reset_core;
    input interrupt_busy;
    integer cycles;
    begin
      @(negedge clk);
      if (interrupt_busy)
        expect_handshake("before_busy_reset", 1'b0, 1'b0);
      reset_n = 1'b0;
      #1;
      expect_handshake("reset_asserted", 1'b1, 1'b0);
      repeat (2) begin
        @(posedge clk); #1;
        expect_handshake("reset_held", 1'b1, 1'b0);
      end
      @(negedge clk);
      reset_n = 1'b1;
      // With no new command, the abandoned operation must never complete.
      for (cycles = 0; cycles < (interrupt_busy ? MAX_CYCLES : 1); cycles = cycles + 1) begin
        @(posedge clk); #1;
        expect_handshake("after_reset", 1'b1, 1'b0);
      end
    end
  endtask

  task begin_check;
    input [8*32-1:0] id;
    begin
      active_checkpoint = id;
      $display("AES_EXT BEGIN %0s", id);
    end
  endtask

  task check_block;
    input [8*32-1:0] id;
    input mode;
    input [127:0] value, expected;
    begin
      start_block(mode, value);
      wait_ready(1'b1);
      $display("AES_EXT RESULT %0s expected=%032h actual=%032h", id, expected, result);
      checked = checked + 1;
      if (result !== expected)
        mismatches = mismatches + 1;
    end
  endtask

  initial begin
    clk = 1'b0;
    reset_n = 1'b1;
    init = 1'b0;
    next = 1'b0;
    encdec = ENCRYPT;
    keylen = AES128;
    key = 0;
    block = 0;
    checked = 0;
    mismatches = 0;

    $display("AES_EXT START v2");
    begin_check("key128_encrypt_first");
    reset_core(1'b0);
    start_init(AES128, KEY128);
    wait_ready(1'b0);
    check_block("key128_encrypt_first", ENCRYPT, P1, C128_1);
    begin_check("key128_reuse_decrypt");
    check_block("key128_reuse_decrypt", DECRYPT, C128_2, P2);
    begin_check("key128_reuse_encrypt");
    check_block("key128_reuse_encrypt", ENCRYPT, P3, C128_3);
    begin_check("key128_reuse_decrypt_again");
    check_block("key128_reuse_decrypt_again", DECRYPT, C128_1, P1);

    begin_check("rekey_128_to_256");
    start_init(AES256, KEY256);
    wait_ready(1'b0);
    check_block("rekey_128_to_256", ENCRYPT, P1, C256_1);
    begin_check("key256_reuse_decrypt");
    check_block("key256_reuse_decrypt", DECRYPT, C256_2, P2);
    begin_check("key256_reuse_encrypt");
    check_block("key256_reuse_encrypt", ENCRYPT, P3, C256_3);
    begin_check("rekey_256_to_128");
    start_init(AES128, REKEY128);
    wait_ready(1'b0);
    check_block("rekey_256_to_128", DECRYPT, REKEY_C, REKEY_P);

    begin_check("reset_during_key_expansion");
    start_init(AES256, KEY256);
    reset_core(1'b1);
    start_init(AES128, KEY128);
    wait_ready(1'b0);
    check_block("reset_during_key_expansion", ENCRYPT, P2, C128_2);

    begin_check("reset_during_block");
    start_block(ENCRYPT, P3);
    reset_core(1'b1);
    start_init(AES256, KEY256);
    wait_ready(1'b0);
    check_block("reset_during_block", DECRYPT, C256_3, P3);

    $display("AES_EXT END checked=%0d mismatches=%0d", checked, mismatches);
    $finish;
  end
endmodule
